"""Diff the GLSL that the Red Book 9e demos embed as string literals.

Twenty of the 33 C++ demos in this repo carry their shaders as adjacent C
string literals (``"#version 410\\n" "uniform ..." ...``) rather than as files
under ``bin/media/shaders/``; the Python ports (``python/<demo>/``) hold the
same shaders as string constants. The file-based shaders are proven verbatim
by the port reading them straight from ``bin/media/shaders/``; this tool is the
equivalent proof for the inline ones (``tasks/reference/python-port/
c-to-python-rules.md``, the verbatim-shader rule).

For every demo directory present on both sides it extracts, in order of
appearance, each string literal (C++: a run of adjacent literals, comments
between pieces ignored; Python: every ``str`` constant) that contains
``#version``, pairs them by position, normalises each pair (the ``#version``
line is dropped — the port may request a different context version — and
trailing whitespace is stripped) and prints a unified diff of what differs.

Usage (from anywhere)::

    python tools/diff_inline_shaders.py [--upstream DIR] [--only 06-cubemap ...] [--quiet]

``--upstream`` is the C++ source root (``<root>/src/<demo>/<demo>.cpp``) and
defaults to this repository, since the C++ lives here alongside the port. Exit
status 1 if any demo differs or has a different shader count.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import pathlib
import re
import sys

REPO: pathlib.Path = pathlib.Path(__file__).resolve().parents[1]  # tools/
PORTS: pathlib.Path = REPO / "python"

# One C string literal, with escapes; adjacent literals may be separated by
# whitespace and // or /* */ comments, which the C++ compiler concatenates.
_LITERAL: str = r'"(?:[^"\\\n]|\\.)*"'
_SEPARATOR: str = r"(?:\s|//[^\n]*\n|/\*.*?\*/)*"
_RUN: re.Pattern[str] = re.compile(
    rf"{_LITERAL}(?:{_SEPARATOR}{_LITERAL})+|{_LITERAL}", re.S
)
_PIECE: re.Pattern[str] = re.compile(_LITERAL)


def _decode_c_literal(piece: str) -> str:
    """The characters a C string literal denotes (common escapes only)."""
    body: str = piece[1:-1]
    return (
        body.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


_DEFINE: re.Pattern[str] = re.compile(
    r"^[ \t]*#define[ \t]+(\w+)[ \t]+((?:[^\n\\]|\\\n|\\.)*)$", re.M
)


def _expand_literal_macros(source: str) -> str:
    """Splice ``#define NAME "..." "..."`` macros (line-continued) into the
    places their name is used, so a shader built as ``"..." NAME "..."``
    (12-raytracer's ``RAY_ELEMENT`` struct) is one literal run."""
    expanded: str = source
    for match in _DEFINE.finditer(source):
        name, body = match.group(1), match.group(2)
        pieces: list[str] = _PIECE.findall(body)
        if not pieces or not _PIECE.sub("", body).replace("\\\n", "").strip():
            # a literal-only body: everything that is not a literal is
            # whitespace and continuation backslashes
            if pieces:
                joined: str = " ".join(pieces)
                # a callable keeps the literals' backslash escapes intact
                # (a template string would turn "\n" into a newline)
                expanded = re.sub(
                    rf"(?<!#define )\b{re.escape(name)}\b",
                    lambda _m: joined,
                    expanded,
                )
    return expanded


def _expand_stringize(source: str) -> str:
    """Turn each ``STRINGIZE( ...body... )`` (12-particlesimulator's
    ``#define STRINGIZE(a) #a``) into a C string literal holding the body's
    raw text. The preprocessor's ``#a`` would collapse the body's whitespace
    onto one line; GLSL does not care, and the readable raw text is what the
    port keeps, so the raw text is the "verbatim" form here."""
    out: str = source
    marker: str = "STRINGIZE("
    start: int = out.find(marker)
    while start != -1:
        depth: int = 1
        i: int = start + len(marker)
        while i < len(out) and depth:
            if out[i] == "(":
                depth += 1
            elif out[i] == ")":
                depth -= 1
            i += 1
        body: str = out[start + len(marker) : i - 1]
        literal: str = (
            '"'
            + body.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            + '"'
        )
        out = out[:start] + literal + out[i:]
        start = out.find(marker, start + len(literal))
    return out


def cpp_shaders(source: str) -> list[str]:
    shaders: list[str] = []
    expanded: str = _expand_literal_macros(_expand_stringize(source))
    for run in _RUN.finditer(expanded):
        text: str = "".join(
            _decode_c_literal(p.group(0)) for p in _PIECE.finditer(run.group(0))
        )
        if "#version" in text:
            shaders.append(text)
    return shaders


def _eval_str(node: ast.expr, consts: dict[str, str]) -> str | None:
    """A string literal, an earlier module-level string name, or a ``+``
    of those -- the shapes the ports use to build a shader source."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left: str | None = _eval_str(node.left, consts)
        right: str | None = _eval_str(node.right, consts)
        if left is not None and right is not None:
            return left + right
    return None


def py_shader_values(tree: ast.Module) -> list[tuple[ast.expr, str]]:
    """Module-level string assignments whose value contains ``#version``,
    in source order, as (value expression, evaluated text)."""
    consts: dict[str, str] = {}
    found: list[tuple[ast.expr, str]] = []
    for stmt in tree.body:
        if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            continue
        if stmt.value is None:
            continue
        text: str | None = _eval_str(stmt.value, consts)
        if text is None:
            continue
        targets: list[ast.expr] = (
            stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
        )
        for target in targets:
            if isinstance(target, ast.Name):
                consts[target.id] = text
        if "#version" in text:
            found.append((stmt.value, text))
    return found


def py_shaders(source: str) -> list[str]:
    return [text for _, text in py_shader_values(ast.parse(source))]


def normalise(text: str) -> list[str]:
    lines: list[str] = [ln.rstrip() for ln in text.splitlines()]
    return [ln for ln in lines if not ln.lstrip().startswith("#version")]


def demo_dirs(upstream: pathlib.Path) -> list[str]:
    cpp_names: set[str] = {p.name for p in (upstream / "src").iterdir()}
    py_names: set[str] = {p.name for p in PORTS.iterdir() if p.is_dir()}
    return sorted(cpp_names & py_names)


def main() -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--upstream", type=pathlib.Path, default=REPO)
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--quiet", action="store_true", help="summary only")
    ns: argparse.Namespace = parser.parse_args()

    failures: int = 0
    for demo in ns.only or demo_dirs(ns.upstream):
        cpp_file: pathlib.Path = ns.upstream / "src" / demo / f"{demo}.cpp"
        py_files: list[pathlib.Path] = sorted((PORTS / demo).glob("*.py"))
        if not cpp_file.exists() or not py_files:
            print(f"{demo:24s} MISSING source on one side")  # noqa: T201
            failures += 1
            continue
        cpp: list[str] = cpp_shaders(cpp_file.read_text(encoding="latin-1"))
        py: list[str] = []
        for f in py_files:
            py.extend(py_shaders(f.read_text(encoding="utf-8")))
        if not cpp and not py:
            print(f"{demo:24s} no inline shaders (file-based)")  # noqa: T201
            continue
        if len(cpp) != len(py):
            print(  # noqa: T201
                f"{demo:24s} COUNT differs: C++ {len(cpp)}, Python {len(py)}"
            )
            failures += 1
            continue
        differing: int = 0
        for index, (c, p) in enumerate(zip(cpp, py, strict=True)):
            diff: list[str] = list(
                difflib.unified_diff(
                    normalise(c),
                    normalise(p),
                    fromfile=f"{demo}.cpp shader {index}",
                    tofile=f"{py_files[0].name} shader {index}",
                    lineterm="",
                )
            )
            if diff:
                differing += 1
                if not ns.quiet:
                    print("\n".join(diff))  # noqa: T201
        verdict: str = (
            "verbatim"
            if differing == 0
            else f"{differing} of {len(cpp)} DIFFER"
        )
        print(f"{demo:24s} {len(cpp)} inline shader(s): {verdict}")  # noqa: T201
        failures += differing
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

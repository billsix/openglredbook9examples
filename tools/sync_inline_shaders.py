"""Make the Red Book ports' inline GLSL byte-equal to the C++ string literals.

Twenty C++ demos embed their shaders as adjacent string literals; the Python
ports (``python/<demo>/``) hold the same shaders as string constants that were
reformatted when they were written (blank lines dropped, long lines wrapped,
comments removed). The verbatim-shader rule (``tasks/reference/python-port/
c-to-python-rules.md``) wants them byte-equal, so this codemod pairs each
``#version`` string literal in a port with the C++ literal at the same
position (as ``diff_inline_shaders.py`` does) and replaces the Python
literal's source text with the decoded C++ text, written as a triple-quoted
string opened with a backslash-newline so the first shader line is line 1.
Shaders listed in ``PORT_EDITED`` are left alone: those are the recorded
port edits whose behaviour has to differ from the C++ (and whose rationale
is in the port file itself).

Idempotent: a second run changes nothing. Usage (from anywhere)::

    python tools/sync_inline_shaders.py [--upstream DIR] [--check] [--only demo ...]

``--upstream`` is the C++ source root and defaults to this repository, since
the C++ lives here alongside the port.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from diff_inline_shaders import (  # noqa: E402
    PORTS,
    REPO,
    cpp_shaders,
    demo_dirs,
    py_shader_values,
)

#: (demo, shader index) pairs that are deliberate port edits, kept as they are.
PORT_EDITED: dict[tuple[str, int], str] = {
    ("12-raytracer", 0): (
        "init shader indexes rays by gl_GlobalInvocationID (the C++ races on "
        "gl_LocalInvocationID) and builds a full-range direction ramp"
    ),
}


def python_literal(text: str) -> str:
    """Source text for ``text`` as a backslash-newline-opened triple-quoted
    string (so the shader's first line is the literal's first line)."""
    if '"""' in text or text.endswith("\\") or text.endswith('"'):
        raise ValueError("shader text cannot be held in a triple-quoted string")
    # the literal's value must be exactly ``text`` (no newline added), or the
    # second run would see a difference and rewrite it again
    return '"""\\\n' + text + '"""'


def sync_file(
    py_file: pathlib.Path, cpp: list[str], demo: str, check: bool
) -> int:
    src: str = py_file.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(src)
    # (value expression, evaluated text): a composed source such as
    # ``HEADER + STRUCT + BODY`` is one shader, and the whole expression is
    # what gets replaced by the single verbatim literal.
    values: list[tuple[ast.expr, str]] = py_shader_values(tree)
    if len(values) != len(cpp):
        print(  # noqa: T201 CLI output
            f"{demo:24s} COUNT differs "
            f"(C++ {len(cpp)}, Python {len(values)}): skipped"
        )
        return 0
    lines: list[str] = src.splitlines(keepends=True)
    offsets: list[int] = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    edits: list[tuple[int, int, str]] = []
    for index, ((node, current), text) in enumerate(
        zip(values, cpp, strict=True)
    ):
        if (demo, index) in PORT_EDITED:
            continue
        if current == text:
            continue
        start: int = offsets[node.lineno - 1] + node.col_offset
        end: int = offsets[(node.end_lineno or node.lineno) - 1] + (
            node.end_col_offset or 0
        )
        edits.append((start, end, python_literal(text)))
    if not edits:
        return 0
    if not check:
        out: str = src
        for start, end, replacement in sorted(edits, reverse=True):
            out = out[:start] + replacement + out[end:]
        ast.parse(out)
        py_file.write_text(out, encoding="utf-8")
    print(  # noqa: T201 CLI output
        f"{demo:24s} {len(edits)} literal(s) {'to sync' if check else 'synced'}"
    )  # noqa: T201
    return len(edits)


def main() -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--upstream", type=pathlib.Path, default=REPO)
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--check", action="store_true")
    ns: argparse.Namespace = parser.parse_args()
    total: int = 0
    for demo in ns.only or demo_dirs(ns.upstream):
        cpp_file: pathlib.Path = ns.upstream / "src" / demo / f"{demo}.cpp"
        cpp: list[str] = cpp_shaders(cpp_file.read_text(encoding="latin-1"))
        if not cpp:
            continue
        for py_file in sorted((PORTS / demo).glob("*.py")):
            total += sync_file(py_file, cpp, demo, ns.check)
    print(f"{total} literal(s) {'would change' if ns.check else 'changed'}")  # noqa: T201
    return 1 if ns.check and total else 0


if __name__ == "__main__":
    sys.exit(main())

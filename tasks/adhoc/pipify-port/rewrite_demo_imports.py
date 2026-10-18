#!/usr/bin/env python3
"""Rewrite flattened demo scripts to import the installed package.

After the port became a pip-installable package (see
``tasks/pythonize-and-containerize-port.md``), the demos no longer need the
``sys.path`` bootstrap. For each ``<name>.py`` in the port dir this codemod:

  * drops the ``PWD = ...`` / ``sys.path.insert(...)`` bootstrap lines,
  * turns the ``import _X  # noqa: E402`` lines into one
    ``from <pkg> import <renamed...>`` (dropping the now-needless noqa), and
  * renames ``_X.`` -> ``<renamed>.`` in the body.

Run ``ruff check --fix`` afterwards to drop the now-unused ``os``/``sys``
imports. A demo already converted (no ``import _X`` lines) is left untouched,
so a second run is a no-op.

Usage (paths relative to the repo root)::

    python tasks/adhoc/pipify-port/rewrite_demo_imports.py \\
        --pkg sb7 --dir python \\
        --map _sb7=application,_common=common,_window=window,_ktx=ktx,_sb6m=sb6m,_colors=colors,_vmath=vmath
"""

from __future__ import annotations

import argparse
import pathlib
import re


def main() -> int:
    ap: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pkg", required=True, help="installed package name")
    ap.add_argument("--dir", required=True, help="dir holding the demo .py")
    ap.add_argument("--map", required=True, help="_old=new,_old=new,...")
    ns: argparse.Namespace = ap.parse_args()

    rename: dict[str, str] = dict(
        kv.split("=") for kv in ns.map.split(",")
    )
    port: pathlib.Path = pathlib.Path(ns.dir)
    changed: int = 0
    for f in sorted(port.glob("*.py")):
        lines: list[str] = f.read_text().splitlines()
        out: list[str] = []
        collected: list[str] = []
        slot: int | None = None
        for ln in lines:
            s: str = ln.strip()
            if s == "PWD = os.path.dirname(os.path.abspath(__file__))":
                continue
            if s == "sys.path.insert(0, os.path.dirname(PWD))":
                continue
            m: re.Match[str] | None = re.fullmatch(
                r"import (_\w+)(\s+# noqa.*)?", s
            )
            if m and m.group(1) in rename:
                collected.append(rename[m.group(1)])
                if slot is None:
                    slot = len(out)
                    out.append("")
                continue
            out.append(ln)
        if slot is None:
            continue
        names: str = ", ".join(sorted(set(collected)))
        out[slot] = f"from {ns.pkg} import {names}"
        text: str = "\n".join(out) + "\n"
        for old, new in rename.items():
            text = re.sub(rf"\b{re.escape(old)}\b", new, text)
        f.write_text(text)
        changed += 1
    print(f"rewrote {changed} demos")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

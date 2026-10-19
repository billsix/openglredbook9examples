# Annotate every binding in the Python port + wire a ty type-gate

## BLUF

Add an explicit type annotation to **every** binding in the `redbook9` Python
port — every module-level global and every local, not just signatures — per the
shared Python standard (`~/.claude/reference/python-coding-standard.md`, "Type
annotations — annotate every binding"). Wire a permanent `ty` +
annotation-completeness gate. "Done" means `make type-check` is green (`ty check`
clean + `check_local_annotations.py --include-module` reports 0), `make check`
still imports all demos, and the work is staged on the `python` branch.

## Context (cold-start)

- Branch: **`python`** (the port; `master`/upstream is the C Red Book 9e samples).
- Layout: shared package `python/redbook9/` + 33 flat demo scripts `python/*.py`
  that `from redbook9 import ...`. Editable-installed (`pip install -e`).
- Baseline gap (2026-10-19): **244 un-annotated bindings** (from repo root:
  `python tools/check_local_annotations.py --include-module python`).
- Standard nuances: loop/unpack targets typed on the line above; read-only
  container params take covariant `Mapping`/`Sequence`; parameterize generics;
  inline single-use values; comprehension loop vars stay inferred; don't fight
  the checker (leave inferred + say why). GL/imgui libs are untyped → `ty` = `Any`.

## Gate (wired this task)

- `tools/check_local_annotations.py` — vendored from runClaudeInContainer canonical.
- Dockerfile installs `ty` (`uv pip install setuptools ty`).
- `make type-check` — `ty check redbook9` + `ty check *.py` + the checker. Needs
  `make image` rebuild first.

## Plan

1. Wire gate (Dockerfile + Makefile + vendored checker). **done**
2. Rebuild image; baseline. (in progress)
3. Annotate the `redbook9` package; verify.
4. Fan out fresh subagents across the 33 demos (git forbidden); verify green.
5. Stage on `python`. (Maintainer commits.)

## Status

**Priority:** 3  **Difficulty:** 6  — **COMPLETE (pending maintainer commit).**

All phases done and verified (2026-10-19):
- 244 un-annotated bindings → **0** (`check_local_annotations.py --include-module`).
- `make type-check` **green**: `ty check redbook9` + `ty check *.py` + checker all pass.
- `make check` imports **33 / 33** demos; `make format` clean (ruff).
- Sweep by 3 fan-out subagents (package + 2 demo batches). The demos needed no
  central `ty` fixes (the `int | Constant` guidance for GL enums was given up
  front). Only fix: the 2 pre-existing glfw strict-stub false positives
  suppressed with `# ty: ignore[invalid-argument-type]` in `redbook9/window.py`
  (the frozen vendored copy) — same as the sibling ports.
- Package subagent modernized `GLenum = int | Constant` to a PEP 695 `type`
  alias and used `Final` for the `common.py` function re-exports.
- A `make format` target + `entrypoint/format.sh` were added (ruff check --fix +
  ruff format); rule 3 (loop/unpack targets) left inferred per the checker's
  exemption.

Staged on the `python` branch — maintainer commits.

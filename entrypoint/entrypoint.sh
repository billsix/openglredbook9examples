#!/bin/env bash
# Default entrypoint: used by `make check`. Imports every demo module as a
# no-display health check (it never opens a window, so it needs no X/Wayland).
# It does NOT build the C (that is `make build-c` / baked in the image / done
# on `make shell`), so `make check` stays a fast Python-only gate. Not a
# correctness check -- a demo that imports clean can still render wrong; that
# needs eyes on a display.

export VIRTUAL_ENV_DISABLE_PROMPT=1
source /venv/bin/activate

cd /openglredbook9/python
# Editable-install the shared `redbook9` package so the demos import it (deps
# are pre-installed in the image).
uv pip install --no-deps --no-index --no-build-isolation -e . \
    --python "$(which python)" >/dev/null

python - <<'PY'
import importlib.util
import pathlib
import sys
import traceback

# Demos are flat scripts at python/<name>.py; they import the installed
# `redbook9` package (no sys.path bootstrap). Import each to catch errors.
port = pathlib.Path("/openglredbook9/python")
files = sorted(port.glob("*.py"))

errors = []
for f in files:
    spec = importlib.util.spec_from_file_location(f"demo_{f.stem}", f)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        errors.append(f.name)
        print(f"FAIL {f.name}")
        print(traceback.format_exc())

print(f"imported {len(files) - len(errors)} / {len(files)} demos")
sys.exit(0 if not errors else 1)
PY

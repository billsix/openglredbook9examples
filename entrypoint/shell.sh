#!/bin/env bash
# `make shell`: build the C against the mounted repo, then drop into an
# interactive shell at the repo root. The container has BOTH display backends:
#   cd python && run 01-triangles    # Python demo — Wayland (or X11), just works
#   run-c 01-triangles               # C example  — forced onto X11 (see below)
# The C examples use gl3w (GLX-only, like GLEW); GLFW picks Wayland when
# WAYLAND_DISPLAY is set and gl3w then cannot resolve GL, so `run-c` launches
# them with WAYLAND_DISPLAY unset (→ X11/XWayland).

export VIRTUAL_ENV_DISABLE_PROMPT=1
source /venv/bin/activate
cd /openglredbook9
loadpackages.sh

# Define the `run` / `run-c` helpers in the interactive shell (sourced from
# ~/.bashrc). Both take a demo DIRECTORY name (e.g. 01-triangles).
cat > /root/.rb9-shell-rc <<'RC'
# Run a Python demo by name. Usage: run 01-triangles
run() {
  if [ -z "$1" ]; then echo "usage: run <demo, e.g. 01-triangles>"; return 2; fi
  local f="/openglredbook9/python/$1.py"
  if [ ! -f "$f" ]; then echo "no such demo: $1"; return 2; fi
  python "$f"
}
# Run a C example by its directory name on X11 (gl3w needs GLX, so Wayland is
# unset). The example loads media via the cwd-relative "media/..." path, so run
# it from the repo's bin/ (where bin/media/ lives). Usage: run-c 01-triangles
run-c() {
  if [ -z "$1" ]; then echo "usage: run-c <example-dir, e.g. 01-triangles>"; return 2; fi
  local bin="/opt/rb9-build/bin/$1"
  if [ ! -x "$bin" ]; then echo "not built: $1 (try: make build-c)"; return 2; fi
  ( cd /openglredbook9/bin && env -u WAYLAND_DISPLAY "$bin" )
}
RC
grep -qxF 'source /root/.rb9-shell-rc' /root/.bashrc 2>/dev/null \
    || echo 'source /root/.rb9-shell-rc' >> /root/.bashrc

echo
echo "Red Book 9e dev shell (repo root: /openglredbook9). Both display backends."
echo "  Python demo:  run <name>                e.g. run 01-triangles   (Wayland)"
echo "  C example:    run-c <name>              e.g. run-c 01-triangles (X11)"
echo "  list demos:   ls python/*.py"
echo

exec bash

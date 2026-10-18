# AGENTS — openglredbook9

OpenGL Programming Guide, 9th edition ("Red Book") sample code: 33 C/C++
examples (`src/`, built by CMake against a `vermilion` static lib in `lib/`,
using glfw + **gl3w** + OpenGL 4.x) plus a behaviour-faithful **Python port**
of all of them (`python/`). Media — textures, `.vbm`/`.dds`/`.bmp` assets and
the GLSL shaders — is tracked once under `bin/media/` and used by both halves.

## Repo shape

- `src/<NN-name>/<NN-name>.cpp` — one C++ example per directory (33). CMake
  (`CMakeLists.txt`) links each to `vermilion` (`lib/`) and names the binary
  after the directory.
- `include/`, `lib/` — the Vermilion framework (gl3w, LoadShaders, vbm/dds/targa
  loaders, vmath).
- `bin/media/` — the assets, loaded by the C examples via the **cwd-relative**
  path `"media/..."` (so a C example runs with cwd = `bin/`). Tracked; the rest
  of `bin/` and all of `build/` are gitignored.
- `python/` — the Python port (below).
- `tasks/`, `tasks/reference/` — task docs and durable knowledge.

## Build and run in a container

The repo-root `Makefile` + `Dockerfile` build **both** halves in one image and
run them with one interface. Standard targets:

```
make image                    # build the image (bakes + compiles the C examples)
make shell                    # repo-root shell, both X11 + Wayland; helpers: run <dir> / run-c <dir>
make run    DEMO=01-triangles # Python port of a demo (Wayland)
make run-c  DEMO=01-triangles # C original (X11)
make build-c                  # (re)build the C examples
make check                    # import every Python demo module, no display
make list                     # list the demo directories
```

Nested podman (inside a runClaudeInContainer/runCrushInContainer sandbox) works
as-is: `PODMAN_RUN_FLAGS` auto-adds `--cgroups=disabled` when `NESTED_PODMAN=1`
is exported. Never pass `NESTED_PODMAN=1` on a downstream command.

### Two display backends, on purpose

The image ships both X11 and Wayland libraries. **The C examples need X11**:
gl3w resolves GL entry points through GLX, which does not exist on an
EGL/Wayland context, so a C demo launched under Wayland opens a window and then
cannot draw. `make run-c` and the in-shell `run-c` helper launch the C binary
with `WAYLAND_DISPLAY` unset (→ X11, or XWayland on a Wayland host). **The
Python port runs on Wayland**: PyOpenGL handles EGL, so `make run` / the `run`
helper stay on Wayland (and also work on X11).

### The C build tree is outside the mount

`make shell` bind-mounts the repo over `/openglredbook9`. The C build tree is
`/opt/rb9-build` (NOT under the mount): the host's own `build/` and
`debugBuild/` carry CMakeCaches configured for the host path, and a build tree
under the mount would collide with them ("source does not match"). The image
bakes + configures `/opt/rb9-build`, so the entrypoint's `cmake --build` on
`make shell` is a fast incremental relink against the live source. CMake writes
the binaries into `/opt/rb9-build/bin`; `run-c` launches them with cwd = `bin/`
so the `"media/..."` paths resolve.

## The Python port

- **A locally editable-installable package** (maintainer's decision,
  2026-10-18). `python/` holds the `redbook9` package of shared modules plus
  flat demo scripts; the container runs `pip install -e python/`, so each demo
  (`python/<NN-name>.py`) imports it with a normal top-of-file
  `from redbook9 import common, application, …` — no `sys.path` bootstrap.
  `redbook9.application.run()` is the entry point. The install is **local and
  editable only** — remote/PyPI distribution is explicitly unwanted (it would
  force packaging the ~266 MB of binary media).
- **Media is referenced, never duplicated.** `python/redbook9/common.py`'s
  `_find_media_dir()` walks up from `python/` to this repo's `bin/media`
  (one level up), so the port needs no env var in or out of the container.
  `REDBOOK9_MEDIA` overrides it. The C shaders live under `bin/media/shaders/`
  and the demos load them from there, matching the C++ byte-for-byte.
- **`python/redbook9/window.py` is vendored** from
  github.com/billsix/modelviewprojection (`ports/openglsuperbiblev4/_common.py`)
  — the window/menubar/camera + imgui helpers the port leans on. It is a frozen
  copy (mvp is the source of truth; re-sync by copying that file over it). Both
  `common.py` and `application.py` import it (`from . import window`).
- **`python/pyproject.toml` defines the package and the lint/type config.**
  `[project]` + `[build-system]` make it editable-installable (`pip install -e
  python/`); `[tool.ruff]` sets line-length 80, `select` = defaults + `T201`.
  `make check` is the headless gate (import every demo); render correctness
  needs a display.

## Cold-start knowledge for the port

Read before touching the port: `tasks/reference/python-port/` (start at its
`README.md`) — the C→Python porting rules, the frameworks (`application`,
`common`, the vendored `window`), the Mesa + PyOpenGL traps (imgui_bundle's
GlfwRenderer not chaining callbacks; the glfw-import ordering; the
binding-qualifier `#version` bump), headless verification, and the per-demo
fidelity audit vs the C++ originals.

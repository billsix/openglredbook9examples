# OpenGL Red Book 9e — Python port

Python translations of the 33 example programs in this repository's C/C++
sources (`../src/`), from the OpenGL Programming Guide, 9th edition (the
"Red Book"). The demos use PyOpenGL + GLFW + imgui_bundle and render the
same pictures as the C++ originals.

This port is a **locally pip-installable package**: `python/` holds the
`redbook9` package of shared modules plus the demo scripts, and the
container runs `pip install -e python/` so the demos import `redbook9`
normally. The install is **local and editable only** — never a remote/PyPI
wheel, because its media (textures, meshes, shaders) is read from the C
sources' own `../bin/media/`, never bundled.

## Run

From the repo root, in the container (builds both C and Python — see the
top-level `README.md`):

```bash
make run DEMO=01-triangles      # a Python demo (Wayland)
make run-c DEMO=01-triangles    # the C original (X11)
make check                      # import every demo, no display
make list                       # list the demos
```

Or directly, in or out of the container, from this `python/` directory
(no env var needed — the media directory is found by walking up to
`../bin/media`, and the `redbook9` package sits beside the script so the
`from redbook9 import …` lines resolve; the container's editable install
puts it on the path too):

```bash
python 01-triangles.py
python 12-simplecompute.py
```

Compute / tessellation demos (chapters 9, 11, 12) need OpenGL 4.3+; the
framework requests 4.3 core by default and a demo overrides
`gl_major`/`gl_minor` if it needs otherwise. To point at a media directory
elsewhere, set `REDBOOK9_MEDIA=/path/to/bin/media` (an override; normally
unnecessary).

## Layout

Each demo is a single `python/<NN-name>.py` script (e.g. `01-triangles.py`)
that imports the shared `redbook9` package. That package (`python/redbook9/`)
holds the infrastructure:

| File           | Purpose |
|----------------|---------|
| `redbook9/application.py` | `Application` base class + `run()` entry point — Python equivalent of `../include/vapp.h`'s `VermilionApplication` |
| `redbook9/common.py`   | Shader compile/link helpers, media resolution (`media_path`), PIL texture loading |
| `redbook9/window.py` | Window/menubar/camera + imgui helpers, vendored from github.com/billsix/modelviewprojection (see the banner in the file) |
| `redbook9/vmath.py`    | numpy-backed translate/rotate/scale/perspective/frustum/ortho/lookat — same shape as `vmath::` |
| `redbook9/vbm.py`      | Pure-Python loader for the `.vbm` mesh format — mirrors `../lib/vbm.cpp` |
| `redbook9/dds.py`   | DDS reader for cube maps and volume textures (PIL handles flat 2D DDS; cubemaps need explicit face-by-face upload) |
| `redbook9/teapot.py`   | Reads the 306 control vertices and 32 patch indices out of `../include/Shapes/Teapot.h` |

## Conventions

- **GLFW + imgui_bundle** for windowing + UI (no GLUT). The `Application`
  class mirrors `VermilionApplication`: `initialize` / `display` / `resize`
  / `on_key` / `on_char` / `finalize` hooks, `main_loop` provided. ESC
  closes; File→Quit and View→Fullscreen (F11) via the imgui menubar; a
  demo's own controls go in a Controls menu (`draw_controls`).
- The framework hooks are snake_case here where `vapp.h` uses CamelCase —
  same hooks, one case convention (house style wins over source fidelity;
  William Emerison Six <billsix@gmail.com>, 2026-07-30). Overrides carry
  `@override`, so a mistyped hook name is a type error, not dead dispatch.
- **Behaviour-faithful:** aspect handling, projection matrices, winding and
  sampler state follow the C++ exactly — e.g. most chapter 3+ demos store
  `aspect = height/width` and call `frustum(-1, 1, -aspect, aspect, …)`;
  don't "fix" the inversion, it is how the C++ matrices work.
- A default VAO is bound after context creation (macOS core profile
  forbids VAO 0); `OpenGL.STORE_POINTERS` is handled before the first GL
  call to avoid an imgui_bundle context-detection failure on Mesa. See
  `../tasks/reference/python-port/mesa-and-pyopengl-traps.md`.

## Fidelity, per-demo risks, and verification

All 33 demos were audited line-by-line against the C++ and brought to
parity; headless back-buffer captures match the C++ build in size and
content class. Correctness still needs **eyes on a display** — an import
smoke test (`make check`) cannot judge a picture.

The per-demo verdicts, the shared root causes that were fixed, the
deliberate deviations (e.g. `12-raytracer`'s work-group indexing, the
`numpy`-seeded particle/fur arrays, the `dds` cubemap reader), and the
remaining things to check on hardware are in
`../tasks/reference/python-port/` — start at its `README.md`, then
`fidelity-audit.md`.

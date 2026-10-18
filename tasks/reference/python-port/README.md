# The Python port — reference set map (L0)

**Reference set** — durable knowledge about the Python port under
[`python/`](../../../python/) of this repository: the C++→Python translation rules
it settled on, the Mesa + PyOpenGL + imgui/GLFW traps met along the way, how to
verify it without a display, and the per-demo fidelity verdict against the C++
originals that sit beside it in [`src/`](../../../src/). Read this first; each row
links down to the doc with the detail. Updated in place, never archived.

This knowledge was harvested from the port's development history — the port was
first written inside the `modelviewprojection` course repository
(github.com/billsix/modelviewprojection) and extracted here so this repository is
the single home for the C++ samples and their port. The docs are rewritten to read
cold against *this* repo alone: everything a fresh contributor needs is in these
docs or the files they point at.

## What the port is

A Python port of the **33** C++ Red Book 9e examples in this repository, using
PyOpenGL + glfw + Dear ImGui (imgui-bundle) and rendering the same scenes. It lives
in `python/` as a **locally editable-installable package**: each demo is a flat
`python/<NN-name>.py` script (e.g. `python 01-triangles.py`) that imports the
`redbook9` package of shared modules (`pip install -e python/`; a local editable
install only, never a remote/PyPI wheel — maintainer's call, William Emerison Six
<billsix@gmail.com>, 2026-10-18).

- Shared infrastructure in the `redbook9` package: `application.py` (the
  `VermilionApplication` framework — glfw + imgui_bundle menubar, lifecycle hooks),
  `common.py` (shader compile/link, media resolution, texture loaders), `vmath.py`,
  `dds.py`, `vbm.py`, `teapot.py`, and `window.py` (a frozen vendored copy of the
  menubar/camera helpers — `frameworks.md` §6).
- **It reuses this repository's own files** rather than shipping copies: the C
  sources' media at [`bin/media/`](../../../bin/media/) (textures, `.dds`, `.vbm`
  meshes) and the GLSL shaders under `bin/media/shaders/`. The ~266 MB media tree is
  referenced, never duplicated (`frameworks.md` §7).
- The C++ originals are right here: each `python/<NN-name>.py` has its
  counterpart in `src/<NN-name>/<NN-name>.cpp` (+ `lib/` framework, `bin/media/`),
  which is what the fidelity audit compares against.

## The docs in this set

| Doc | One breath |
|---|---|
| `c-to-python-rules.md` | The settled C++→Python rules: the type table, imgui-widgets-not-keyboard (menubar Controls menu, F11, Esc), "set" a uniform vs "upload" a buffer, inline small fixtures, **shaders are the C++ build's** (§8), **keyword every argument a callee accepts, and which PyOpenGL functions cannot** (§10). |
| `frameworks.md` | What the shared modules provide: `application.Application` (lifecycle + `run`), `common` (shader + media + texture helpers), `vmath`/`dds`/`vbm`/`teapot`, and the vendored `window` (why it's a frozen copy and where the source of truth is). |
| `mesa-and-pyopengl-traps.md` | The modern-GL failure modes on Mesa + PyOpenGL and the imgui/GLFW integration traps: the `contextdata` patch, GlfwRenderer not chaining callbacks, `import glfw` first, `glMemoryBarrier`, fragment-shader interlock, `glClearTexImage`, the `#version` bump, the viewport-array collapse, and the DDS/sampler-state rules. |
| `headless-verification.md` | What `make check` (the import smoke test) proves and what it cannot, the back-buffer capture method for a real render check, and the X11/Wayland backend agreement a headless run needs. Correctness needs a display. |
| `fidelity-audit.md` | Per-demo verdict (faithful / drift / gap / broken) of all 33 Python demos vs the C++, the eleven cross-cutting root causes, the deliberate deviations, and the finding → fix table. All findings are fixed; kept as the record and the latent-risk list. |

## Verification status

Every Python demo was audited line-by-line against its C++ original and every
finding fixed (see `fidelity-audit.md`). `make check` imports all 33 demo modules
without a display and so catches import-time and asset-resolution failures; it
cannot confirm the picture matches — that needs a display, which is the
maintainer's to run (the on-display pass is the open item `fidelity-audit.md` records).

## Related (elsewhere in this repo)

- [`python/README.md`](../../../python/README.md) — the per-demo run notes.
- [`README.md`](../../../README.md) / [`Makefile`](../../../Makefile) — the
  container commands (`make image` / `shell` / `run` / `run-c` / `check` / `build-c`).
- [`AGENTS.md`](../../../AGENTS.md) — the repository working contract.

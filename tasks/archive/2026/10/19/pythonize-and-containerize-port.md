# Bring the Python port into this repo + containerize C and Python together

## BLUF

The Python port of these Red Book 9e samples currently lives **inside the
`modelviewprojection` repo** (github.com/billsix/modelviewprojection) at
`ports/openglredbook9/`. Move it here so this repo is the single home for both
the C/C++ samples and their Python port, add a top-level container that builds
**both** halves, and delete the port from mvp. "Done" means: `python/` holds the
port, runnable in and out of the container with no env var; the C examples and
the Python demos both build/run from one `make` interface; the cold-start
knowledge the port depended on (mvp reference docs) is harvested here; and mvp
no longer mentions redbook9.

This mirrors the McNopper extraction already done in github.com/billsix/OpenGL
(a C example repo with a `python/` port, a top-level `Dockerfile`/`Makefile`/
`entrypoint/`, and `tasks/reference/python-port/` cold-start docs). Differences
from that job are called out inline — they are what make this not a copy-paste.

## Context (cold-start)

- **This repo** (`openglredbook4.5.git`): C/C++ Red Book 9e samples. CMake
  (`CMakeLists.txt`) builds a `vermilion` static lib + 33 example executables
  into `${CMAKE_BINARY_DIR}/bin`; media (textures, `.vbm` meshes, `.dds`,
  GLSL shaders) is tracked under `bin/media/`. Uses glfw3 + **gl3w** (not GLEW)
  + OpenGL 4.x. `.gitignore` ignores `build/*` and `bin/*` except `bin/media/`.
  Not containerized before this task.
- **The port** (now `python/`, extracted from mvp `ports/openglredbook9/`): 33
  demos, each a flat `python/<NN-name>.py` script that imports the
  editable-installable `redbook9` package at the top of the file
  (`from redbook9 import common, application, …`);
  `redbook9.application.run(cls, title)` is the entry point. The `redbook9`
  package holds `common.py`, `application.py` (the `VermilionApplication`
  framework, glfw + imgui_bundle menubar), `vbm.py`, `teapot.py`, `vmath.py`,
  `dds.py`, and the vendored `window.py`. Packaged as a **local editable
  install** (maintainer's call 2026-10-18).

### The three things that differ from the McNopper extraction

1. **The port is not self-contained.** `common.py` AND `application.py` load
   `ports/openglsuperbiblev4/_common.py` from mvp at import time (for
   `WindowState` / `draw_menubar` / `Camera` / `toggle_fullscreen` / imgui
   setup). That v4 module imports only stdlib + glfw + OpenGL + imgui_bundle
   (no `modelviewprojection`, no gacalc), so it is vendorable. **Fix:** vendor
   v4's `_common.py` into the package as `python/redbook9/window.py` and import
   it from the siblings (`from . import window`). v4 stays in mvp untouched;
   this repo gets a frozen copy that will drift from mvp's over time (inherent
   to being an independent repo).
2. **The duplication is ~266 MB, not 181 bytes.** The port carries a
   byte-identical copy of this repo's entire `bin/media/` (121 files; verified
   `diff -rq` empty). **Fix:** `common.py`'s `_find_media_dir()` already
   ancestor-walks — reorder it to prefer this repo's `bin/media` (i.e.
   `../bin/media` from `python/`) and delete the in-port copy.
3. **Escape/menubar need no fix.** `application.py` already chains the imgui
   GlfwRenderer callbacks and draws File→Quit / View→Fullscreen. (McNopper
   needed a central fix; redbook9 does not.)

## Plan (phases; each is a staging/commit boundary)

1. **This task doc.** (done when staged)
2. **Port in + self-contained + media dedup.** Copy mvp `ports/openglredbook9/`
   → `python/`; move the shared modules into the `redbook9` package and vendor
   v4 `_common.py` as `python/redbook9/window.py` (imported `from . import
   window` by `common.py`/`application.py`); reorder `_find_media_dir()` to
   prefer `../bin/media`; delete `python/bin/media` (the 266 MB dup). Add
   `python/requirements.txt` (PyOpenGL, glfw, imgui-bundle, numpy, Pillow) and
   the `pyproject.toml` package + ruff config / gitignore bits.
3. **Container at top level.** `Dockerfile` (Fedora + C toolchain + GL/EGL +
   BOTH X11 and Wayland dev/runtime libs; build the C into `/opt/rb9-build`
   OUTSIDE the mount to dodge the CMakeCache-collision gotcha; install the
   Python deps). `Makefile` (`image`/`shell`/`run DEMO=`/`run-c DEMO=`/`check`/
   `build-c`/`clean`). `entrypoint/` scripts. Editable install of the
   `redbook9` package (`pip install -e python/`). Templated from
   github.com/billsix/OpenGL, adapted to CMake→`bin/` and gl3w.
4. **Cold-start docs + tooling.** Harvest the parts of mvp's shared
   `tasks/reference/ports/*` that apply to redbook9 into
   `tasks/reference/python-port/`; bring the redbook9-specific tooling
   (`tools/redbook9/` — inline-shader sync, A/B capture).
5. **README + AGENTS.** Commands-forward README section; AGENTS build/run +
   cold-start pointers.
6. **Remove from mvp.** `git rm` the port + redbook9-only docs/tools; scrub the
   shared `tasks/reference/ports/*`; re-point `tools/keywordify.py`
   (`DEFAULT_TREE`) and `tasks/adhoc/moreports-headless-verification/
   headless_sweep.py` (`TREES`) off redbook9; fix `entrypoint/format.sh`,
   `pyproject.toml`, `CLAUDE.md`.
7. **Gates + sweep + stage.** Build the container, headless-import the demos,
   run mvp's gates, reconcile always-read docs, stage everything (do NOT
   commit — maintainer commits).

## Decisions

- **Local editable install, not flat run-by-path** (maintainer, 2026-10-18).
  `python/` is an editable-installable `redbook9` package (`pip install -e
  python/`); remote/PyPI distribution stays explicitly unwanted (it would force
  packaging the binary assets), so the install is local-only and media is
  referenced from `bin/media`, never bundled.
- **Media referenced, never bundled** — same as McNopper's `Binaries/` model.
- **McNopper (github.com/billsix/OpenGL) is left as-is** — its local editable
  install is wanted; nothing to undo there.

## Status

**Priority:** 3  **Difficulty:** 6

Landed and staged in this repo (2026-10-18, William Emerison Six
<billsix@gmail.com>'s session):

- Phase 2 ✓ — port copied to `python/`; shared modules moved into the
  `redbook9` package and the v4 helpers vendored as `python/redbook9/window.py`
  (imported `from . import window` by `common.py` and `application.py`); media
  dedup done (`_find_media_dir` prefers `../bin/media`; no in-port copy);
  `requirements.txt` / `.gitignore` / the `pyproject.toml` package + ruff
  config (line-length 80, select defaults + T201) added. One `uloc = lambda` →
  nested `def`, five diagnostic prints `# noqa: T201`; `ruff check` +
  `ruff format --check` clean (41 files).
- Phase 3 ✓ — top-level `Dockerfile` / `Makefile` / `entrypoint/`
  (`entrypoint.sh` import gate, `loadpackages.sh` C build, `shell.sh` with
  `run`/`run-c`). `make image` builds (33 C binaries + `libvermilion.a`);
  `make check` = **imported 33 / 33 demos**.
- Phase 4 ✓ — cold-start set in `tasks/reference/python-port/` (6 docs);
  `tools/diff_inline_shaders.py` + `tools/sync_inline_shaders.py` carried over
  and adapted (now default to this repo; `diff` reports all verbatim bar the
  one recorded 12-raytracer edit, `sync --check` = 0). The A/B frame-capture
  harness (`ab_capture.sh`/`swapshot.c`) was NOT carried — it drove mvp's
  `render_probe.py`; see `verify-port-visually.md`.
- Phase 5 ✓ — `README.md` (container + Python-port sections), `AGENTS.md`,
  `python/README.md` rewritten commands-forward and standalone.
- Phase 6 (mvp removal) — done on the mvp side (port, tooling, redbook9-only
  docs `git rm`'d; shared docs scrubbed; `verify-port-visually.md` moved here);
  staged in the mvp repo for the maintainer's commit.
- Phase 7 ✓ — mvp format + type-check gates run against the existing image:
  ruff check/format all green and reformatted nothing; `ty` green on
  src/tests/codetheclassics/v7 and the annotation checker passed. The only red
  is 2 pre-existing `pygltflib` unresolved-import diagnostics in demo22b (a
  stale local image that predates that dep — not touched here; `make image`
  fixes it). Session sweep done: CLAUDE.md / reference docs / READMEs
  reconciled across both repos; the McNopper/OpenGL repo untouched.

Nothing is committed (the maintainer commits); this repo's additions are
staged. When committed, this task archives to `tasks/archive/…`.

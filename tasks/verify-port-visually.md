# Display-check the Red Book 9e Python-port parity fixes

**Status:** blocked
**Priority:** 4
**Difficulty:** 2
**Created:** 2026-10-14 (the display pass the maintainer has to run); moved into
this repo from github.com/billsix/modelviewprojection on 2026-10-18 when the
Python port was extracted here.
**Blocked on:** a real display — the maintainer running each demo and the C++
original side by side.
**Recheck:** `make run DEMO=10-viewport-array` on a display: four ninjas in
four quadrants = the pass has started; this task closes when every row below is
confirmed (or a regression is filed).

## BLUF

A 2026-10-14 fidelity audit (now `tasks/reference/python-port/fidelity-audit.md`)
changed what most of the 33 Red Book Python ports draw or how they respond to
keys. The fixes are code-reviewed, gate-green and were captured headless against
the C++ build (`glReadPixels` on both sides), but only one of the 33 had ever
been seen on a display before (12-raytracer, 2026-05-02). This task is the
maintainer's pass: run each demo next to its C++ original and confirm the rows
below. "Done" = every row confirmed good, or a regression recorded in the audit
doc with a new task.

## How to run

In the container (builds both halves):

    make run   DEMO=<demo>      # the Python port (e.g. make run DEMO=01-triangles)
    make run-c DEMO=<demo>      # the C++ original

Or directly: `cd python && python <demo>/<name>.py` for the port; for the C++,
`make build-c` then `cd bin && /opt/rb9-build/bin/<demo>` (inside the shell), or
on the host build it with `cmake -S . -B build -G Ninja && cmake --build build`
and run from `bin/`. Every port opens at the C++'s 800×600; the imgui menubar
is the one visible addition.

## Rows, in priority order

| demos | look for |
|---|---|
| ESC in any demo; M in 01-keypress, 04-gouraud, 04-gouraud-float, 09-simpletess; I/K/O/L/R/M in 09-teapot; R in 11-oit, 11-overdrawcount, 11-doublewrite | keys work at all (they were dead: wired before imgui's callbacks) and each has its widget |
| 10-viewport-array | four ninjas in four quadrants, every frame (was: all four in the bottom-left) |
| 06-volumetexturing | the cloud tiles across the quad as it rotates (was: smeared edge voxels) |
| 06-load-texture, 06-multitexture | image orientation matches the C++ (was: vertically mirrored) |
| the nine demos with controls (01-keypress, 03-primitiverestart, 04-gouraud, 04-gouraud-float, 09-simpletess, 09-teapot, 11-doublewrite, 11-oit, 11-overdrawcount) | the widgets are in the menubar's Controls menu (no floating panel over the drawing); 09-teapot's sliders show their whole labels; every demo: View → Fullscreen and F11 both toggle fullscreen |
| 04-shadowmap | the lit disc on the ground has the C++'s radius over the orbit (`lookat` quirk reproduced); note the C++ itself shows almost nothing on Mesa (its FBO uses the depth-stencil attachment) |
| 09-simpletess, 09-teapot | patch/teapot size matches the C++ (`mat.h` perspective); the teapot is whole in the port and 19/32 patches in the C++ on purpose |
| 01-keypress, 01-triangles, 04-gouraud, 04-gouraud-float, 06-statictexture, 06-texturewrapping, 08-lightmodels | 4:3 proportions as the C++ (window size) |
| 11-doublewrite | the two copies overlap and clip at the window edges as in the C++ (±200 px at 800×600) |
| 12-raytracer | tiled gradient (render shaders verbatim again); the ramp itself is the recorded port edit |
| 12-particlesimulator | the initial cloud is a dense-centred ball; 8.4 M particles as the C++ |
| 03-pointsprites | coloured sprite in the port, grey in the C++ (C++ TGA bug, deliberate) |
| the 13 FAITHFUL demos | unchanged picture apart from the window size |

## Notes

- Headless back-buffer captures from the fix session were the baseline; they
  agreed in size and content class but animation phase differs, so they are
  triage, not proof. The A/B frame-capture harness (`ab_capture.sh`, which drove
  an mvp `render_probe.py`) was NOT carried into this repo — it was coupled to
  mvp's probe. The inline-shader verbatim check DID come across:
  `tools/diff_inline_shaders.py` (and `tools/sync_inline_shaders.py`).

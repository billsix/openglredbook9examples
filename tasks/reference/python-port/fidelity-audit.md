# Python port — fidelity audit vs the C++ originals (L2)

Up: `README.md`. **What is TRUE about each Python demo in `python/` relative to its C++
original** — the `src/<demo>/<demo>.cpp` (+ the `lib/` framework, `include/`, and the shader
files under `bin/media/shaders/`) that sits beside it in this repository — compared for
constants and resources, render structure and GL state, uniforms and attributes (counted per
program), animation, controls (C++ keys → imgui widgets, `c-to-python-rules.md` §3),
simplifications, and outright bugs. Audited 2026-10-14 by six read-only reader passes (five
batches of demos, one for the shared framework). Anchors are file + symbol; **line numbers
rot, so the file + symbol is the anchor.**

**Verdict scale:** FAITHFUL (same picture, same controls) · MINOR DRIFT (cosmetic/constant
differences a viewer might notice) · FUNCTIONAL GAP (a feature/control/pass missing or
approximated) · BROKEN (cannot be producing the C++'s picture).

**Status:** every finding below was fixed the same day ("Fix status" at the end maps finding →
fix), except the ones recorded as deliberate deviations. The scoreboard and per-demo findings
describe the state BEFORE the fixes and are kept as the record and the latent-risk list.
Headless back-buffer captures match the C++ build in size and content class; the maintainer's
on-display pass is the remaining open item, and until then "fixed" means code-reviewed,
gate-green and captured headless, not seen on a display.

## Scoreboard (33 of 33, before the fixes)

| Verdict | Demos |
|---|---|
| FAITHFUL (13) | 03-drawcommands, 03-instancing, 03-instancing2, 03-instancing3, 03-primitiverestart, 03-xfb, 06-cubemap, 10-draw-xfb, 10-fur, 11-oit, 11-overdrawcount, 12-imageprocessing, 12-simplecompute |
| MINOR DRIFT (18) | 01-keypress, 01-triangles, 03-pointsprites, 04-gouraud, 04-gouraud-float, 04-shadowmap, 06-load-texture, 06-mipfilters, 06-mipmap, 06-multitexture, 06-statictexture, 06-texturewrapping, 08-lightmodels, 09-simpletess, 09-teapot, 11-doublewrite, 12-particlesimulator, 12-raytracer |
| FUNCTIONAL GAP (1) | 06-volumetexturing |
| BROKEN (1) | 10-viewport-array |

("Window size" alone accounts for most of the MINOR DRIFT column.) Separately, the framework
reader found that **every key in every demo was dead** (root cause 1), which no per-demo reader
could see from the source of one demo.

## Cross-cutting root causes (fixed once, in the framework)

1. **Key callbacks were wired before imgui installed its own** (`application.run` called
   `_wire_callbacks()` before `init_imgui()`; imgui_bundle's `GlfwRenderer` replaces the GLFW
   key/char callbacks and does not chain — `mesa-and-pyopengl-traps.md` §2). ESC-to-close in all
   33 demos and the `on_key` hooks of 8 demos (01-keypress, 04-gouraud, 04-gouraud-float,
   09-simpletess, 09-teapot, 11-doublewrite, 11-oit, 11-overdrawcount) never fired. Fix: wire
   after `init_imgui`, forwarding key and char events to imgui's handlers first.
2. **Window size.** `vermilion.cpp`'s `Initialize` opens **800×600**; `application.run` opened a
   1920×1080 default and never read `Application.initial_width/height`. The 15
   `frustum(-1, 1, -aspect, aspect, …)` demos lost 25 % of the scene top and bottom; the NDC
   demos (01-*, 04-gouraud*, 06-load-texture, 06-statictexture, 06-texturewrapping,
   06-multitexture, 06-volumetexturing) stretched 4:3 → 16:9; 08-lightmodels' hard-coded 1.333
   aspect drew a fat torus; 11-doublewrite's ±200 px shift changed its composition; the
   `gl_FragCoord / textureSize` demos (12-simplecompute, 12-imageprocessing) tiled differently.
   Fix: `run()` opens at `initial_width/height` (800×600).
3. **`load_texture_2d` flipped rows** (`FLIP_TOP_BOTTOM`) where the C++ `vglLoadTexture` uploads
   DDS rows raw; 06-load-texture and 06-multitexture were vertically mirrored vs the C++. For
   the TGA of 03-pointsprites the flip restores the raw bottom-up order and matches. Fix: the
   DDS callers go through `dds.upload_2d` (file rows, file mips); the PIL path keeps its flip
   for TGA.
4. **`dds.upload_*` and `load_texture_2d` imposed sampler state** (`LINEAR_MIPMAP_LINEAR`,
   `CLAMP_TO_EDGE`) where `vglLoadTexture` sets none; 06-volumetexturing sampled with CLAMP
   where the C++ tiles the cloud with GL's default REPEAT (it rotates texture coordinates out of
   `[0,1]³`), 06-cubemap and 03-pointsprites were filtered differently. Fix: the uploaders set
   no sampler state; each demo sets exactly what its C++ sets (`mesa-and-pyopengl-traps.md` §14).
5. **`vmath.lookat` normalised `s` and `u`; `vmath::lookat` does not**, so the C++ view matrix
   scales eye x/y by `sin∠(f, up)`. Only caller 04-shadowmap: the C++ light frustum covers a
   1.1–1.7× wider footprint over the orbit. Fix: mirror the C++ (comment names the quirk).
6. **Angel's `include/mat.h` `Perspective`/`Frustum` leave `c[3][3] = 1`** → clip `w = 1 − z`;
   09-simpletess and 09-teapot (the only `mat.h` includers) drew 11–30 % larger in the port.
   Fix: `vmath.perspective_mat_h`, used by those two.
7. **imgui's state restore collapses the viewport array** (`glViewport` sets every index):
   10-viewport-array drew all four ninjas in the bottom-left quadrant from frame 2. Fix:
   re-issue the four `glViewportIndexedf` each frame (`mesa-and-pyopengl-traps.md` §11).
8. **`vbm.VBObject.load` unpacked the 100-byte new-format header** while every SBM1 file
   declares `size = 92`; `num_materials`/`flags` read "posi"/"tion" from the attribute table
   (unused by any demo). Fix: copy `min(size, sizeof)` bytes and zero-fill, as `vbm.cpp`.
9. **Inline shaders.** 20 C++ demos embed GLSL as string literals; the ports' copies were
   reformatted (blank lines, wraps, comments), all logic-identical except the recorded port
   edits below. Four ports inlined shaders their C++ loads from `bin/media/shaders/`
   (01-keypress, 01-triangles, 04-gouraud, 04-gouraud-float). Fix: file loading for those four;
   the other 48 literals were made byte-equal to the C++ text (re-verify by diffing a demo's
   literal against `src/<demo>/<demo>.cpp`).
10. **Rules §3 unapplied tree-wide:** only 03-primitiverestart had a widget. Fix: wireframe
    checkboxes (01-keypress, 04-gouraud, 04-gouraud-float, 09-simpletess, 09-teapot), Inner/Outer
    sliders + reset (09-teapot), "Reload shaders" buttons (11-oit, 11-overdrawcount,
    11-doublewrite); keys stay as accelerators; `KEY_R` added to `application.Application`.
11. **Mesa barriers missing on the pattern `mesa-and-pyopengl-traps.md` §4 records:**
    12-simplecompute and 12-imageprocessing (`imageStore` → `texture()` without
    `GL_TEXTURE_FETCH_BARRIER_BIT`), 12-particlesimulator (compute-written attribute buffer
    without `GL_VERTEX_ATTRIB_ARRAY_BARRIER_BIT`). Fix: barriers added.

## Per-demo findings (before the fixes; condensed from the readers' reports)

- **01-keypress MINOR DRIFT.** Window (NDC triangles 4:3→16:9); shaders inlined where the C++
  loads `media/shaders/keypress/*`; M = wireframe key only (and dead, root cause 1).
- **01-triangles MINOR DRIFT.** As 01-keypress (files `triangles.{vert,frag}`); the port's
  docstring claimed file loading. The C++ uses `glCreateBuffers`+`glBufferStorage` (4.4/DSA),
  the port `glGenBuffers`+`glBufferData` — same bytes, same picture; C++ `main` is raw GLFW (no
  ESC, no viewport on resize).
- **03-drawcommands FAITHFUL.** Loads the same `primitive_restart/*.glsl` files; 2/5 uniforms,
  four draw commands incl. `glDrawElementsBaseVertex(basevertex=1)` and `glDrawArraysInstanced`.
- **03-instancing / 03-instancing2 / 03-instancing3 FAITHFUL.** Instance counts 200/100/100,
  TBOs, `glUniformMatrix4fv(loc, 4, …)` via `upload_array`, per-instance `mat4` columns; the
  C++'s `Finalize` deletes never-created handles (03-instancing) and has a dead `lookat`
  (03-instancing2). Title nit: "Instancing 2 Example".
- **03-pointsprites MINOR DRIFT, in the port's favour.** The C++ `lib/targa.cpp` `swapUint32`
  assigns byte 1 to all four bytes, so every 32-bpp TGA renders as (G,G,G,G): the C++ sprite is
  grey, the port's (PIL) is coloured. **Deliberate deviation.** `_xorshift_floats` reproduces the
  C++ RNG so the four points match. The C++ binary aborts (rc 134) under Mesa in the headless
  A/B run.
- **03-primitiverestart FAITHFUL.** The compile-time `USE_PRIMITIVE_RESTART` is a checkbox (the
  house pattern).
- **03-xfb FAITHFUL.** Four literals logic-identical; TF varyings; 5000 seed points from
  `RandomState(0x13371337)` instead of the C++ LCG (same distribution, cosmetic).
- **04-gouraud / 04-gouraud-float MINOR DRIFT.** Window; shaders inlined where the C++ loads
  `gouraud/*`; M key only. Vertex strides differ (20 vs 12, 28 vs 20) but are self-consistent.
- **04-shadowmap MINOR DRIFT (medium).** `lookat` normalisation (root cause 5). Two C++ bugs the
  port corrects, kept: `GL_DEPTH_STENCIL_ATTACHMENT` on a depth-only texture (FBO incomplete on
  Mesa — the C++ draws almost nothing headless, 3 colours) and `Resize` without `glViewport`.
- **06-cubemap FAITHFUL.** DDS path verified (A8R8G8B8, 11 mips, face order = GL order); sampler
  state differed (root cause 4).
- **06-load-texture MINOR DRIFT.** Vertical flip (root cause 3); window.
- **06-mipfilters / 06-mipmap MINOR DRIFT.** Window only. The C++ draws two 8-index strips from
  a 4-index buffer (out of bounds) and 06-mipmap's `Reshape` is not an override, so its `aspect`
  is uninitialised — the port draws the intended picture (deliberate). Texel nit: 1/255 in
  G/B/A where the C++ overflows.
- **06-multitexture MINOR DRIFT.** Row flip ×2 (root cause 3); C++ `GL_RGB8` + file mips vs the
  port's `GL_RGBA8` + regenerated mips (now the file's); tex2 filter (root cause 4).
- **06-statictexture / 06-texturewrapping MINOR DRIFT.** Window only (checker cells 1.78:1).
- **06-volumetexturing FUNCTIONAL GAP.** CLAMP vs REPEAT wrap (root cause 4).
- **08-lightmodels MINOR DRIFT.** Hard-coded 1.333 aspect on a 16:9 window (root cause 2). The
  C++ fetches three colour uniforms it never sets; the port fetches two — same program state.
  Shader: the port had renamed a VS local (`position` → `pos`); now verbatim.
- **09-simpletess MINOR DRIFT.** `mat.h` perspective (root cause 6); M key only.
- **09-teapot MINOR DRIFT.** `mat.h` perspective; `teapot.py` data verified identical to
  `Teapot.h`. **The C++ draws 306 of the 512 indices** (`NumTeapotVertices` where it means
  `NumTeapotIndices`): 19 of 32 patches. The port draws the whole teapot — **deliberate
  deviation**. Keys I/K/O/L/R/M only (now widgets too). No depth test on either side.
- **10-draw-xfb FAITHFUL.** TF with `gl_NextBuffer`, `glDrawTransformFeedbackStream`; the C++
  trusts uniform location 0 (`mesa-and-pyopengl-traps.md` §7), the port queries it.
- **10-fur FAITHFUL.** 30 layers; fur texture from `RandomState(0)` instead of `rand()`
  (cosmetic).
- **10-viewport-array BROKEN.** Root cause 7.
- **11-doublewrite MINOR DRIFT.** ±200 px composition (root cause 2); the FS is an inline,
  interlock-guarded edit of `double_write.fs.glsl` (recorded port edit,
  `mesa-and-pyopengl-traps.md` §5); the C++ zero-PBO clear is undersized (reads past the PBO) and
  the port uses `glClearTexImage` (`mesa-and-pyopengl-traps.md` §6).
- **11-oit / 11-overdrawcount FAITHFUL.** R key only (and the C++ 11-oit compares against ASCII
  114, so its own R is dead); both sides leak programs on reload.
- **12-imageprocessing FAITHFUL.** `curiosity.dds` is RGBA32F (FourCC 116) on both sides;
  docstring said RGBA8/Sobel. Fetch barrier (root cause 11).
- **12-particlesimulator MINOR DRIFT.** Count IS the C++'s 8,388,608 (docstring said reduced);
  initial distribution was a cube where `random_vector` gives a ball — now a ball. The C++ UBO
  is undersized (512 B for a 1024 B block; harmless). Barrier (root cause 11).
- **12-raytracer MINOR DRIFT, deliberate.** The C++ init shader indexes its ray buffer by
  `gl_LocalInvocationID` (1024 work groups race on 256 slots; the trace pass then reads mostly
  never-written memory) and draws a flat per-tile blue; the port indexes by
  `gl_GlobalInvocationID` and builds a full-range direction ramp — the **one recorded inline
  port edit** (`INIT_SOURCE`). Its render shaders had also been edited to stretch the 512²
  image (UV) where the C++ tiles it (`gl_FragCoord / textureSize`); those are verbatim again.
- **12-simplecompute FAITHFUL.** Fetch barrier (root cause 11).

## Deliberate deviations (keep; do not "fix" the port toward the C++)

Core-profile 4.3 forward-compatible context (the C++ requests nothing and gets Mesa's 4.6
compatibility context; no demo uses compat-only calls); the default VAO; the `binding` version
bump (inert for this tree: its `binding` users are already `#version 420/430 core`); shader
files decoded `errors="replace"`; ESC closes the window (the C++ base `OnKey` is empty);
stricter shader error handling (`ShaderError` vs the C++'s silent 0/black); the Mesa barriers,
`glClearTexImage` and interlock of `mesa-and-pyopengl-traps.md` §4–6; the colour TGA of
03-pointsprites; the whole teapot of 09-teapot; 06-mipmap's initialised aspect; 04-shadowmap's
`GL_DEPTH_ATTACHMENT`; 12-raytracer's init shader; `vbm` honouring `index_type` and offsetting
old-format attributes correctly where the C++ aliases them; numpy RNG seeds (03-xfb, 10-fur,
12-particlesimulator).

## Fix status (applied; display check pending)

| Finding | Fix |
|---|---|
| Root cause 1, dead keys | `application.run` wires callbacks after `init_imgui`, forwarding to imgui's `keyboard_callback`/`char_callback` |
| Root cause 2, window | `application.run` opens at `initial_width/height` (800×600) |
| Root cause 3, row flip | 06-load-texture, 06-multitexture → `dds.upload_2d` |
| Root cause 4, sampler state | `dds.upload_2d/3d/cubemap` and `load_texture_2d` set none; 06-load-texture and 06-multitexture tex1 set `LINEAR_MIPMAP_LINEAR` as the C++ |
| Root cause 5, `lookat` | no normalisation of `s`/`u` |
| Root cause 6, `mat.h` | `vmath.perspective_mat_h` in 09-simpletess, 09-teapot |
| Root cause 7, viewports | 10-viewport-array re-issues the four viewports per frame |
| Root cause 8, VBM header | `size`-bounded, zero-filled unpack |
| Root cause 9, shaders | 4 demos load the C++'s files; 48 literals synced verbatim; 2 recorded edits |
| Root cause 10, widgets | 8 demos gained panels; `KEY_R` |
| Root cause 11, barriers | 12-simplecompute, 12-imageprocessing, 12-particlesimulator |
| 12-particlesimulator seed | ball distribution via `_random_vectors` |
| Docstrings | 12-particlesimulator, 12-imageprocessing, 11-oit, 09-teapot, `teapot.py`, 06-mipmap |

Not changed on purpose: the latent `vmath.rotate` arity landmines (2-arg `rotate(angle,
vec3)` rotates about Z; all 46 callers use the 4-arg form), `ortho`'s `tz` sign (no caller),
the C++-side bugs listed above, the `resize`-after-`initialize` ordering (21 harmless
`self.aspect = 1.0` placeholders), `swap_interval(1)` (matters only for 03-xfb's per-frame
counter and only off Mesa).

## Controls: every C++ control, and its widget

The C++ framework (`lib/vermilion.cpp`) wires a GLFW key callback and a char callback only; no
demo reads the mouse, the scroll wheel or a GUI toolkit. Eight demos override `OnKey`; every
key has a widget in the port, drawn in the menubar's Controls menu by the demo's
`draw_controls` (`c-to-python-rules.md` §3), and the key stays as an accelerator.

| demo | C++ keys | port widget |
|---|---|---|
| 01-keypress, 04-gouraud, 04-gouraud-float, 09-simpletess | M: toggle `GL_LINE`/`GL_FILL` | checkbox "Wireframe (M)" |
| 09-teapot | I/K: inner tess level ±1, clamped 1–64; O/L: outer, same; R: both to 1; M: wireframe | two `slider_float` 1–64, button "Reset to 1 (R)", checkbox |
| 11-doublewrite, 11-overdrawcount | R: `InitPrograms()` | button "Reload shaders (R)" |
| 11-oit | `case 'r'` (ASCII 114; GLFW delivers `GLFW_KEY_R` = 82, so the C++ key never fires) | button "Reload shaders (R)", and `KEY_R` works in the port |
| 03-primitiverestart | none at runtime; `#define USE_PRIMITIVE_RESTART 1` at compile time | checkbox "Use GL_PRIMITIVE_RESTART" (a port addition, kept) |
| the other 24 | none | no panel |

## How to use this doc

Fixes went shared-helpers-first, then per demo; the shaders are the C++ build's
(`c-to-python-rules.md` §7) except the two recorded edits; the maintainer's display pass is the
open item. If a demo is later found to differ from the C++, record the new finding here and
open a task for it. Re-verify a changed inline shader by diffing it against
`src/<demo>/<demo>.cpp`, and capture a frame next to the C++ build (`headless-verification.md`
§4).

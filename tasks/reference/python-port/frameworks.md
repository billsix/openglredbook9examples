# The port framework — what the shared modules provide (L2)

Up: `README.md`. The port keeps each demo readable top-to-bottom and pushes the machinery a
C++ demo got for free from `VermilionApplication` (and the `lib/` support code) into a few
modules in the `redbook9` package (`python/redbook9/`). This doc is the map of those modules: what each
provides and how they fit together. Facts are from the source under `python/`.

## 1. `application.py` — the `VermilionApplication` port

`Application` is the base class with the C++ virtuals as overridable hooks: `initialize(title)`,
`display(auto_redraw)`, `resize(width, height)`, `finalize()`, `on_key(key, scancode, action,
mods)`, `on_char(codepoint)`, plus `app_time()` in milliseconds like the C++. `run(cls, title)`
is the `DEFINE_APP` + `main()` entry point: it does the GLFW init / window / context dance,
then calls the demo's `initialize` / `resize` / loop / `finalize`. GLFW key codes are
re-exported as `Application.KEY_*` so a demo never imports glfw.

Decisions baked into the base class and `run`, several learned the hard way:

- **Opens at 800×600** (`initial_width`/`initial_height`, overridable per class) — the C++
  `vermilion.cpp` opens 800×600 for every demo, and the NDC demos, the
  fixed-horizontal-FOV frustums and the `gl_FragCoord`/`textureSize` tilings all draw a
  different picture at any other size.
- **GL context is 4.3 core, forward-compatible** (`gl_major`/`gl_minor`) — compute and
  tessellation need 4.3; the C++ requests nothing and gets Mesa's 4.6 compatibility context,
  but no demo uses compat-only calls.
- **A default VAO is created and never unbound** (`_make_default_vao`) — macOS Core Profile
  prohibits VAO 0.
- **No `glUseProgram(0)` in the loop** — 09-simpletess and 09-teapot bind their program once
  in `initialize` and never again, and unbinding between frames makes the next
  `glUniformMatrix4fv` an `INVALID_OPERATION`; no demo in this tree deletes a currently-bound
  program, so the hot-reload reason to reset to 0 does not apply
  (`mesa-and-pyopengl-traps.md` §12).
- **No base-class `aspect` attribute** — 21 demos assign it; a `@property` there broke all of
  them (`c-to-python-rules.md` §4).
- **The `contextdata` monkey-patch** runs before `import OpenGL.GL`
  (`mesa-and-pyopengl-traps.md` §1), and **GLFW key/char callbacks are wired *after*
  `init_imgui`** and forward to imgui's handlers first (`mesa-and-pyopengl-traps.md` §2).
- **`resize` receives framebuffer PIXELS** via `set_framebuffer_size_callback`, not the
  window-size callback (HiDPI — `mesa-and-pyopengl-traps.md` §2). A `gl_FragCoord`-sized FBO
  or image target must use these.

`main_loop` draws the menubar (`window.draw_menubar`), calls the demo's `display`, then
imgui's draw, then swaps — so the menu appears over the demo. imgui's per-frame GL-state
restore uses `glViewport`, which rewrites every viewport in the array: a demo using
`glViewportIndexedf` (10-viewport-array) must re-issue its viewports each frame.

## 2. `common.py` — shaders, media, textures

- **Media resolution** (§7): `MEDIA_DIR`/`media_path(*relative)` and `_find_media_dir`.
- **Shader pipeline:** `compile_shader`, `compile_program(vs=…, fs=…, gs=…, tcs=…, tes=…,
  cs=…)` from inline strings, `compile_program_from_files(...)` from paths, and
  `link_program(shaders, tf_varyings=…, tf_buffer_mode=…)` — the only correct way to call
  `glTransformFeedbackVaryings` from PyOpenGL (`mesa-and-pyopengl-traps.md` §9). A
  `ShaderError` carries the driver info log. `_ensure_binding_qualifier_version` bumps a
  `layout(binding)` shader's `#version` to 420 at load (inert for this tree; §8 of the traps
  doc). Shader files are read `encoding="utf-8", errors="replace"` (traps §10).
- **Texture loaders:** `load_texture_2d(filename, generate_mipmaps=…)` goes through PIL for
  the C++'s TGA path (flips rows to GL's bottom-up order like `lib/targa.cpp`) and
  `load_cubemap(face_filenames)`. DDS goes through `dds` (§4). Like both C++ loaders, these
  set no sampler state beyond what a demo needs — each demo sets exactly what its C++ sets.
- The `GLenum = int | Constant` alias (`c-to-python-rules.md` §2) is defined here.

## 3. `vmath.py` — `vmath::` as numpy

`vec3`/`vec4`, `translate`/`scale`/`rotate`, `perspective`/`frustum`/`ortho`/`lookat`, and
`upload(loc, mat)` which passes `transpose=GL_TRUE` to convert row-major numpy to GLSL's
column-major layout. Degrees for `rotate`, right-handed projections, matching `vmath.h`. One
quirk worth knowing: `lookat` does **not** normalise `s`/`u` (matching `vmath::lookat`, which
scales eye x/y by `sin∠(f, up)` — only 04-shadowmap depends on it), and
**`perspective_mat_h`** reproduces Angel's `include/mat.h` `Perspective` (which leaves
`c[3][3] = 1`, clip `w = 1 − z`) for the two demos that include it, 09-simpletess and
09-teapot.

## 4. `dds.py` — the DDS reader PIL cannot replace

A hand-rolled DDS reader: `upload_2d`, `upload_cubemap`, `upload_3d`, supporting uncompressed
RGBA8/BGRA8 and DXT1/3/5 (uploaded compressed via `glCompressedTexImage2D`). It exists because
PIL's DDS plugin **flattens cubemaps and volumes to a single slice** without warning, so
06-cubemap and 06-volumetexturing need the reader to walk the header and upload each
face/slice itself, keeping the file's own row order and mip chain like the C++
`lib/vdds.cpp`/`loadtexture.cpp`. It sets no sampler state.

## 5. `vbm.py` / `teapot.py` — mesh data

`vbm.VBObject.load(filename, vertex_index=…, normal_index=…, tex0_index=…)` reads the `.vbm`
mesh format (new-format `SBM1` magic, old-format fallback), uploads the attribute blob in one
`glBufferData`, and sets contiguous (not interleaved) attribute pointers — mirroring
`lib/vbm.cpp`, including copying `min(size, sizeof)` header bytes and zero-filling. `teapot.py`
holds the Utah teapot's 306 control vertices and 32 patch indices inlined
(`c-to-python-rules.md` §6).

## 6. `window.py` — the vendored menubar/camera helpers (a frozen copy)

`window.py` is a **frozen vendored copy** of `ports/openglsuperbiblev4/_common.py` from the
`modelviewprojection` repository (github.com/billsix/modelviewprojection), where the port was
first written. Those helpers are mvp-wide (a shared menubar, imgui setup, window sizing,
fullscreen, a walk-around camera), not Red-Book-specific, so they were copied in rather than
reimplemented when the port was extracted here. **modelviewprojection is the source of truth;
re-sync by copying that file over this one, and do not reshape it to this repo's style** (the
banner at the top of the file says so). Because it is an independent copy it will drift from
mvp's over time — that is inherent to this repo standing alone.

Both `common.py` and `application.py` import it as a package sibling (`from . import window`).
`application.py` imports it **after** its `contextdata` monkey-patch and first `import
OpenGL.GL`; the `# noqa: E402` at that import marks the deliberate ordering (§1,
`mesa-and-pyopengl-traps.md` §1), not a path bootstrap.

What the two modules take from it: `WindowState`, `draw_menubar(window, state, controls=…)`,
`draw_view_menu`, `poll_fullscreen_key`/`toggle_fullscreen` (F11), `init_imgui`,
`resolve_default_window_size`, and `Camera`/`apply_camera`/`update_camera`/`bind_camera_inputs`/
`draw_camera_controls`. The camera helpers are re-exported for parity; the Red Book demos
manage their own view matrices through `vmath` and mostly do not use the walk-around camera.
`MVP_CONTROLS_WINDOW` (the headless hook of `headless-verification.md`) is read here.

## 7. Media resolution — the one rule

Nothing hardcodes an absolute path. `common._find_media_dir()` returns `(path, tried)` and
resolves in order:

1. `$REDBOOK9_MEDIA`, if set and a directory (override).
2. **`<repo>/bin/media`** — one directory up from `python/`, the C sources' own media. This
   is the normal case and needs no env var, in the container or on a host checkout.
3. `<port>/bin/media` — a copy dropped into the port directory (not normally present).
4. A 12-level ancestor walk for a sibling/cousin `openglredbook9`/`redbook9` checkout, then a
   few common dev-box locations.

The ~266 MB of textures/meshes/shaders lives in exactly one place — this repo's `bin/media/` —
and is **referenced, never duplicated** under `python/`. `media_path(*relative)` raises
`FileNotFoundError` listing every path it tried when nothing matches.

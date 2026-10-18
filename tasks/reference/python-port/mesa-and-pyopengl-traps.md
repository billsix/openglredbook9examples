# Mesa + PyOpenGL and imgui/GLFW traps (Python port) (L2)

Up: `README.md`. The failure modes met porting shader-era, compute-era C++ (Red Book 9e) to
PyOpenGL + imgui-bundle on a **Fedora / Mesa radeonsi / Wayland** box, plus the imgui/GLFW
integration traps. Each cost a debugging round; several are invisible on NVIDIA or AMD
proprietary drivers, which is why the C++ originals never needed them. Check here before
writing or debugging GL/imgui/GLFW code in the port. Code paths are under `python/`.

## 1. PyOpenGL "no valid context" → patch `contextdata`

`imgui_bundle`'s `GlfwRenderer.__init__` dies in its first `glVertexAttribPointer(…,
c_void_p(offset))` because PyOpenGL's pointer-retention bookkeeping asks
`OpenGL.platform.GetCurrentContext()` and Mesa returns 0 even after GLFW made the context
current. The old fix (`OpenGL.STORE_POINTERS = False`) is **silently ignored** by current
PyOpenGL unless `ERROR_ON_COPY` is also on, which would break every list-argument
`glUniform*fv` call. The fix, applied in `application.py` *before the first `import OpenGL.GL`*,
makes the per-context bucket constant:

```python
import OpenGL.contextdata as _contextdata
_contextdata.getContext = lambda context=None: context if context is not None else 1
import OpenGL.GL as GL   # AFTER the patch
```

Retention degenerates to one global table, harmless because the port keeps its buffers alive
on instance attributes. Two companions: issue **one GL call after `make_context_current` and
before `init_imgui`** (the `glGetString` vendor/version prints in `application.run` are load-bearing,
not decoration), and never call `glBindVertexArray(0)` — a default VAO stays bound for the
process lifetime (macOS Core Profile prohibits VAO 0).

## 2. imgui's GlfwRenderer installs its own GLFW callbacks and does NOT chain

`GlfwRenderer(window)` installs its own GLFW key/char/cursor callbacks in its constructor and
does not chain to any previously-installed ones — whatever you set with
`glfw.set_key_callback` *before* constructing it is silently discarded. The symptom when this
is wrong: **Escape does not quit and no demo key works**, while the menubar still responds.
`application.run` therefore wires its callbacks **after** `init_imgui`, and each one forwards to
imgui's handler (`impl.keyboard_callback` / `char_callback`) before running the demo's hook —
so imgui keeps its input *and* the demo's keys fire. (Wiring them before was the bug that took
out every key in 18 ports on an earlier display pass.)

And wire the **framebuffer-size** callback, not the window-size callback: the window-size
callback delivers screen coordinates, which under HiDPI / fractional scaling are smaller than
the framebuffer, so `glViewport` fed with them draws the scene into the bottom-left `1/scale`
of the window with black bars. `application._wire_callbacks` uses `set_framebuffer_size_callback`
and seeds once from `get_framebuffer_size()` after startup.

A bare `imgui.begin(title)` floating window is also a trap — imgui auto-fits it once, sizing
each slider to ~65 % of a near-zero first-frame width, and the saved `imgui.ini` (written to
the cwd) then pins the narrow size. The port avoids this entirely by putting every demo's
widgets in the menubar's Controls menu (`c-to-python-rules.md` §3).

## 3. `import glfw` before `import imgui_bundle` in every module that imports imgui

The first GLFW loaded into the process wins. imgui-bundle ships its own `libglfw.so.3`, an
**X11-only** build; if its native module loads first, pyglfw binds that copy, the window gets
a GLX context through XWayland, and PyOpenGL — which picks its EGL backend purely from
`WAYLAND_DISPLAY` — sees no current context. Its extension check then fails, so every GL 4.2+
function `OpenGL.GL` exposes as an ARB alias (`glBindImageTexture`, `glMemoryBarrier`,
`glTexStorage2D`, `glDispatchCompute`) raises `NullFunctionError` while `glGetString` still
says "4.6". `application` imports glfw before imgui, so a demo that only imports `application`/`common` is
covered; a module that imports `imgui_bundle` directly carries `import glfw  # noqa: F401`
above it. The container's Makefile also exports `PYGLFW_LIBRARY=/usr/lib64/libglfw.so.3` (the
system dual-backend build), which masks the problem — so a green container run is not evidence
the import order is right; keep the rule.

## 4. Mesa needs the `glMemoryBarrier` the proprietary drivers insert for you

Two programs sharing an image-load-store target (or SSBO, or atomic counter) across
draws/dispatches show **artifacts that look like z-fighting** — a partially-flushed image.
Insert the barrier between them:

| After … then … | Barrier bit |
|---|---|
| `imageStore` in one program, read in another | `GL_SHADER_IMAGE_ACCESS_BARRIER_BIT` |
| SSBO write, SSBO read | `GL_SHADER_STORAGE_BARRIER_BIT` |
| atomic counter write, read | `GL_ATOMIC_COUNTER_BARRIER_BIT` |
| compute `imageStore`, then `texture()` sampling | `GL_TEXTURE_FETCH_BARRIER_BIT` |
| compute-written attribute buffer, then draw | `GL_VERTEX_ATTRIB_ARRAY_BARRIER_BIT` |
| compute → CPU readback (`glGetBufferSubData`) | `GL_BUFFER_UPDATE_BARRIER_BIT`, and prefer `glFinish()` |

12-simplecompute and 12-imageprocessing (`imageStore` → `texture()`) and 12-particlesimulator
(compute-written attributes) all needed barriers the C++ omits.

## 5. Overlapping fragments in ONE draw race on `imageStore` → fragment-shader interlock

Barriers between draws do not order fragments *within* a draw. Proprietary drivers happen to
raster-order; Mesa does not, so the same pixel gets a different "last writer" each frame
(shimmer). Fix in GLSL: `#extension GL_ARB_fragment_shader_interlock`,
`layout(pixel_interlock_ordered) in;`, and wrap the `imageStore`s in
`beginInvocationInterlockARB()` / `endInvocationInterlockARB()`. **Do not add it to shaders
that already use `imageAtomic*`** — atomics serialize on their own (why 11-oit and
11-overdrawcount are left alone). **Make it `: enable` + `#ifdef`, not `: require`** — radeonsi
supports the extension but **llvmpipe does not**, so a `require` turns the shader into a
compile error there; guarded, it degrades to the upstream's unordered behaviour. 11-doublewrite
is the one demo that needs it (its interlock-guarded inline fragment shader is a recorded port
edit, `c-to-python-rules.md` §7).

## 6. Clear a texture with `glClearTexImage`, not a zero PBO + `glTexSubImage`

The C++ clears by uploading from a zero-filled `GL_PIXEL_UNPACK_BUFFER` sized at
`sizeof(GLuint)` per pixel — **undersized for RGBA32F** (16 bytes/pixel). Proprietary drivers
tolerate the short read; Mesa rejects with `INVALID_OPERATION`. `glClearTexImage(tex, 0,
GL_RGBA, GL_FLOAT, None)` (4.4+) is one call with no size to get wrong (11-doublewrite).

## 7. `glUniform*(0, …)` — location 0 is not reliably yours

Some C++ demos write to location 0 for a uniform with no `layout(location=0)`. NVIDIA-style
drivers hand the first scalar uniform location 0; Mesa does not and rejects with
`INVALID_OPERATION`. **Always `glGetUniformLocation` after linking**, even where the C++
hard-codes 0 (10-draw-xfb trusts location 0 in the C++; the port queries it). Uniform *blocks*
with `layout(binding=N)` are fine.

## 8. GLSL rewrites applied to shaders at load (the shader text stays verbatim)

The shaders are the C++ build's (`c-to-python-rules.md` §7); these rewrites happen in the
*loader*, not the text:

- **`layout(binding = N)` on samplers needs `#version 420`.** A shader that says `410 core`
  and uses it compiles on permissive drivers and fails on Mesa ("unrecognized layout
  identifier 'binding'"). `common._ensure_binding_qualifier_version` bumps the `#version`
  line. (Inert in this tree — every `binding` user is already `420/430 core` — but kept
  because the reader is shared with files that could need it.)
- **Integer interface-block members need `flat`.** An `int material_id;` inside an `out VS_OUT
  {…}` without an interpolation qualifier compiles on NVIDIA and fails on Mesa; a shader that
  hits this needs `flat` injected (with a negative lookahead so it never emits `flat flat`).

## 9. `glTransformFeedbackVaryings` from PyOpenGL

PyOpenGL type-checks the third argument as `LP_LP_c_char`; no list of `str`/`bytes` satisfies
it directly. `common.link_program(tf_varyings=…, tf_buffer_mode=…)` builds the
`create_string_buffer`s and the `POINTER(c_char)` array and keeps them referenced until
`glLinkProgram` returns (default mode `GL_INTERLEAVED_ATTRIBS`). Request transform feedback
through that keyword (03-xfb, 10-draw-xfb); never call the raw function.

## 10. Upstream shader files are not all UTF-8

An upstream shader can carry a Latin-1 byte (e.g. `©`, 0xA9) in a copyright comment; the C++
handed the compiler raw bytes, Python's default decode raises `UnicodeDecodeError`.
`common` reads shaders with `encoding="utf-8", errors="replace"`. When grepping for such
bytes use **`LC_ALL=C grep -P`** — under a UTF-8 locale `grep -P "[\x80-\xff]"` skips invalid
bytes and reports nothing.

## 11. imgui's state restore collapses the viewport array

imgui_bundle's GL backend restores state with `glViewport`, which sets **every** index of the
viewport array. A demo using `glViewportIndexedf` (10-viewport-array) must re-issue its
viewports each frame, or from frame 2 everything draws in the bottom-left quadrant. Indexed
state, colour/depth masks, rasterizer discard, image units and patch parameters are also not
saved/restored by the backend; polygon mode, depth/cull/blend enables, program, VAO, unit-0 2D
texture and the two buffer bindings are.

## 12. Don't put `glUseProgram(0)` in the loop

Red Book demos bind their program once in `initialize` and never again (09-simpletess,
09-teapot); unbinding between frames makes the next `glUniformMatrix4fv` an
`INVALID_OPERATION`. No demo in this tree deletes a currently-bound program, so there is no
hot-reload reason to reset to 0 — `application.main_loop` deliberately does not.

## 13. DDS: PIL silently flattens cubemaps and volumes

PIL's DDS plugin reads a flat 2D DDS fine but **flattens cubemaps and volumes to one slice**
without warning. `dds.upload_cubemap`/`upload_3d` walk the header themselves and upload each
face/slice, needed by 06-cubemap and 06-volumetexturing. Three format paths: uncompressed
RGBA8/BGRA8, and DXT1/3/5 via `glCompressedTexImage2D`.

## 14. Loaders set no sampler state; watch texture row order and wrap

`vglLoadTexture` (the C++ `lib/loadtexture.cpp`) sets no sampler state and uploads DDS rows
raw. `dds.upload_2d`/`load_texture_2d` follow suit: each demo sets exactly the filter/wrap its
C++ sets. Imposing `LINEAR_MIPMAP_LINEAR`/`CLAMP_TO_EDGE` by default was wrong —
06-volumetexturing needs GL's default `REPEAT` to tile the cloud (it rotates texture
coordinates out of `[0,1]³`). The DDS path keeps the file's own row order; the PIL/TGA path
flips to GL's bottom-up order like `lib/targa.cpp`.

## Where each rule is enforced in code

| Rule | Code |
|---|---|
| §1 contextdata patch, default VAO | `application.py` (top-of-module patch), `application._make_default_vao` |
| §2 callbacks after imgui, framebuffer size | `application._wire_callbacks` |
| §8 version bump | `common._ensure_binding_qualifier_version` |
| §9 transform-feedback varyings | `common.link_program(tf_varyings=…)` |
| §10 shader decode | `common.compile_shader_from_file` / `compile_program_from_files` |
| §13 cubemap/volume upload | `dds.upload_cubemap` / `upload_3d` |
| §14 sampler state, row order | `common.load_texture_2d`, `dds.upload_2d` |

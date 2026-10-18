# C++ → Python: the settled rules for the port (L2)

Up: `README.md`. The rules the Python port under `python/` settled on, translating this
repository's C++ Red Book 9e examples (`src/<NN-name>/<NN-name>.cpp` + the `lib/`
framework). **Behaviour-faithful throughout:** nothing here may change GL call order, RNG,
or what is drawn. Code paths are under `python/`.

## 1. Structure follows the C++, names follow Python

Each demo keeps its C++ original's *shape* — a class per demo overriding the
`VermilionApplication` lifecycle hooks — so a reader can hold `src/<NN>/<NN>.cpp` and
`python/<NN>.py` side by side. The hooks are renamed to Python house style, which is
safe because the *Python* base class (`application.Application`) defines the hook, so the name is
ours:

| C++ (`vapp.h`) | Python | Note |
|---|---|---|
| `Initialize` / `Display` / `Resize` / `Finalize` | `initialize` / `display` / `resize` / `finalize` | overrides carry `@override` |
| `OnKey` / `OnChar` / `MainLoop` | `on_key` / `on_char` / `main_loop` | |
| `m_pWindow` | `window` | member-prefix convention has no Python meaning |

`@override` is not decoration: a hook whose name drifts from the base becomes a type error
instead of silently-dead dispatch, and `make check` imports every demo so the mismatch is
caught.

## 2. The type table (C++ / vmath → Python)

| C / library type | Python | Note |
|---|---|---|
| `GLuint`, `GLint`, `GLsizei` | `int` | names, locations, counts |
| `GLenum` | `GLenum = int \| Constant` | the alias threaded through `common`/`dds` — PyOpenGL constants are `IntConstant`, so a bare `int` annotation on a GL enum needs a suppression; the alias avoids them |
| `GLfloat` / `GLboolean` / `GLchar*` | `float` / `bool` / `str` | |
| `GLfloat[16]`/`[9]`/`[3]`/`[4]`, `vmath::vec*`/`mat4` | `np.ndarray` | 4×4 **row-major**, transposed at upload (`vmath.upload` passes `GL_TRUE`) |
| the DDS header | a dataclass (`dds.DDS`) | |
| a GLFW window handle | `Any` | **the one sanctioned `Any`** — glfw's stubs type it as an opaque pointer |

Two footguns: `glGen*(1)` returns an `int` but `glGen*(n>1)` returns an array — annotate
only the `(1)` form; and treat any other `Any` as "I didn't check" — leave the name bare
instead. **Typing found real bugs by counting:** count the `glUniform*` calls per program
against the C++'s `glGetUniformLocation`s (08-lightmodels fetched colour uniforms the C++
never sets — same program state, but the count is the check).

## 3. Every adjustable parameter is an imgui widget; keys are accelerators at most

A C++ `case 'M': mode = GL_LINE/GL_FILL;` becomes an `imgui.checkbox`; `I/K/O/L` stepping a
tessellation level become `imgui.slider_float`s; `case 'R': InitPrograms();` becomes a
button. **Show the widget — do not write "press M to toggle" in the panel.**

**The widgets live in the menubar's Controls menu, never a floating window** (the
maintainer's call, William Emerison Six <billsix@gmail.com>, 2026-10-14: a floating panel
overlaps the drawing, and a bare `imgui.begin` saves a too-narrow size that `imgui.ini` then
pins — `mesa-and-pyopengl-traps.md` §2). The menubar is `File → Quit (Esc)`, `View →
Fullscreen (F11, polled from the keyboard)`, `Controls → the demo's widgets`. A demo overrides
`draw_controls(self)` on its `application.Application`; `main_loop` adds a Controls menu only when
a demo defines one. A menu body runs only while the menu is open, so apply a change on the
spot or store it on `self` — never rely on it running every frame. The key stays as an
accelerator in `on_key`. Headless gates set `MVP_CONTROLS_WINDOW=1`, which also draws the
body in a plain window every frame so every widget executes (`headless-verification.md`).

## 4. What a framework base class may and may not define

Do **not** pre-define, as a `@property`, an attribute demos assign to. An early `aspect`
read-only property on `application.Application` **broke 21 demos** — they all write
`self.aspect = …` in `initialize`, exactly as the C++ does, and `vapp.h` defines no such
member either. Leave the attribute to the demo or give it a plain default in `__init__`. The
comment in `application.py` saying "Don't add one back" is load-bearing.

## 5. "Set" a uniform; "upload" a buffer or a texture

`glUniform*` specifies program state (it moves no bytes to GPU memory); `glBufferData`/
`glTexImage*` do. So helpers are named `set_uniforms`, and "upload" is reserved for VBO
creation (`vbm`), texture loads (`common`/`dds`), and UBO `glBufferSubData`.

## 6. Inline small static fixtures; never parse a C++ header at runtime

The Utah teapot's control points (306 verts × 3, 32 patches × 16 indices, ~5 KB) live as
Python tuples in `teapot.py`, not a regex over `include/Shapes/Teapot.h` at runtime — a
reader needs the media tree but not the C++ include tree. Same for anything you would
otherwise read out of the C++ source at runtime. (`teapot.load`'s data is verified
numerically equal to the header.)

## 7. The shaders are the C++ build's; parity work is Python-side

**Every shader a port runs is the shader its C++ binary runs.** This repo holds it in two
forms:

- **(a) The 13 demos whose C++ loads `media/shaders/*`** load the same files through
  `common.compile_program_from_files`, reading straight from this repo's
  `bin/media/shaders/<demo>/` — byte-identical to what the C++ compiles (01-keypress,
  01-triangles, 03-drawcommands, 03-pointsprites, 03-primitiverestart, 04-gouraud,
  04-gouraud-float, 04-shadowmap, 09-simpletess, 09-teapot, 11-doublewrite, 11-oit,
  11-overdrawcount).
- **(b) The 20 demos whose C++ embeds GLSL as string literals** hold the decoded literal
  text in a module-level Python string, byte-equal to the C++ — re-verify against
  `src/<demo>/<demo>.cpp` after any edit. `tools/diff_inline_shaders.py` mechanizes this
  (pairs each port literal with the C++ at the same position and diffs, ignoring `#version`);
  `tools/sync_inline_shaders.py [--check]` rewrites a drifted port literal back to the C++
  text (skipping the recorded port edits below). Both default to this repo.

Never hand-reduce, "simplify", restyle or re-derive a shader; if the port needs different
behaviour, that is a Python-side change (uniforms, texture formats/units, GL state, camera).
Decided by the maintainer (William Emerison Six <billsix@gmail.com>, 2026-10-13) after a
hand-written PBR shader hid two Python-side bugs behind shading differences (learned porting
the SuperBible trees in modelviewprojection).

**Recorded port-edited shaders** — the only two inline literals that deliberately differ from
the C++, and anything else that differs is a bug:

- **12-raytracer's `INIT_SOURCE`** indexes rays by `gl_GlobalInvocationID` where the C++ races
  on `gl_LocalInvocationID` (1024 work groups on 256 slots), and builds a full-range direction
  ramp instead of the C++'s flat per-tile blue.
- **11-doublewrite's inline fragment shader** adds the `GL_ARB_fragment_shader_interlock`
  guard of `mesa-and-pyopengl-traps.md` §5.

The `#version` is otherwise the C++'s; `common._ensure_binding_qualifier_version` would bump
a `layout(binding)` shader below 420 at load, but every `binding` user in this tree is already
`#version 420/430 core`, so the bump is inert here (`mesa-and-pyopengl-traps.md` §8).

## 8. Keyword arguments at every call site that can take them

Every call whose callee accepts keyword arguments passes them by keyword, under one
mechanical rule (maintainer's call, William Emerison Six <billsix@gmail.com>, 2026-10-14):

- **Project APIs and keyword-capable library calls keyword every argument:** the port's own
  functions and dataclasses, PyOpenGL's Python-level convenience functions
  (`glBufferData(target=…, size=…, data=…, usage=…)`, `glVertexAttribPointer`,
  `glGetUniformLocation`, `glDeleteTextures`, …), imgui-bundle
  (`imgui.slider_float(label=…, v=…, v_min=…, v_max=…)`) and glfw.
- **Library callees keep required leading parameters positional** and keyword only those with
  a default: `np.zeros((3,), dtype=…)`, `open(path, mode="rb")`. `np.cross(a, b)` and
  `re.sub(p, r, s)` stay as they are. **Single-argument and `*`/`**`-splat calls are left
  alone.**

**What cannot take keywords, and stays positional — do not "finish the job" by hand:**
PyOpenGL 3.1.10's raw ctypes functions (`glUseProgram`, `glBindTexture`, `glUniform*f/i`,
`glEnable`, `glViewport`, `glClearColor`, `glDrawArrays`, …) and its array-converting wrappers
(`glGen*`, `glDrawElements`, `glTexImage2D/3D`, `glUniformMatrix4fv`, `glGetIntegerv`, …) raise
`TypeError` on a keyword argument. numpy ufuncs (`np.sin`, `np.radians`), numpy scalar
constructors and `math.*` take no keywords either. Classify by probing the live GL object
(`_NullFunctionPointer`/`Wrapper` in its MRO = positional only; an `OpenGL.lazywrapper` =
keywords by its Python signature), never by a hand list. This is a convention, not a gate
(ruff has no rule for it).

## 9. Gates for any edit to the port

`ruff` clean and format-idempotent at line-length 80; `ty` clean; and `make check` must still
import all 33 demos (which executes `@override` and the import-time media resolution). For
anything that changes what is drawn, a back-buffer render before/after and, when possible, an
A/B capture against the C++ build (`headless-verification.md`). Correctness ultimately needs
the maintainer's display.

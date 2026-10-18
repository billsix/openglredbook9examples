# Headless verification of the port (method) (L2)

Up: `README.md`. How to exercise the demos without a display or a real GPU, what that proves
and what it cannot. The cheap check this repo ships is `make check`; a real render check is a
**method** (the capture harness from the port's development history was not carried into this
repository — rebuild from the description here if you need it).

## 1. What a no-display run can and cannot tell you

| Class | Findable headlessly? | How |
|---|---|---|
| **IMPORT** — the module fails to import, or its asset paths don't resolve | yes | `make check` exit code + traceback |
| **CRASH** — the demo raises before or during its first frames | yes | non-124 exit code + stderr tail |
| **BLANK** — a window opens and nothing is drawn | yes | ≤3 distinct colours in a back-buffer capture |
| **RENDERED** — a plausible picture | yes, that it *exists* | >3 colours |
| *Correct* — matches the C++ original | **no** | needs the C++ frame side by side (§4) or a human |

`RENDERED` means *worth a human look*, not *right*. A no-display run shortens the on-display
pass; it does not replace it — the fidelity verdicts in `fidelity-audit.md` all needed the
maintainer's display, the open item that doc records.

**`make check`** is the shipped cheap gate: it imports all 33 demo modules against the
referenced `bin/media/` without opening a window, catching import-time and asset-resolution
failures. It never renders, so it cannot tell a working demo from a blank one. (It runs the
default container entrypoint, `entrypoint/entrypoint.sh`.)

## 2. A real render check: Xvfb + the backend agreement

A GLFW demo has no natural exit: run it under `timeout N` and treat **rc 124 as success**;
anything else non-zero is a crash. Judge pixels, never exit codes — a blank window exits
exactly like a working one.

The load-bearing detail is that **GLFW's backend and PyOpenGL's backend must agree.** PyOpenGL
picks EGL when `WAYLAND_DISPLAY` is set and GLX when it is not; GLFW 3.4 prefers Wayland when
the socket is present and falls back to X11 when it is not. If they disagree, PyOpenGL sees no
current context and every ARB-aliased GL 4.2+ entry point (`glTexStorage2D`,
`glBindImageTexture`, `glDispatchCompute`, `glViewportIndexedf`) raises `NullFunctionError`
while `glGetString` still answers "4.6 (Core Profile) Mesa". For a headless run:

- `Xvfb :99 -screen 0 1280x800x24 &`, share `/tmp/.X11-unix` into the container,
  `-e DISPLAY=:99`.
- **Unset `WAYLAND_DISPLAY`** so GLFW falls back to X11 (its window then lives on Xvfb) and
  PyOpenGL lands on GLX to match. `application.run` does not itself pin a GLFW platform, so the
  environment is what makes the two agree. Leaving a mounted `wayland-0` visible points GLFW at
  the maintainer's own compositor: the window appears on their desktop, and while their screen
  is off the compositor sends no frame callbacks, so every swap blocks and the run stalls.
- Set `MVP_CONTROLS_WINDOW=1` to also draw each demo's Controls-menu body in a plain window
  every frame, so every widget executes headlessly (`c-to-python-rules.md` §3).

## 3. When X captures are black: photograph the back buffer

On recent Mesa a GL window's pixels may not reach Xvfb at all (`import -window root` is one
colour even inside the container). The demo can still be photographed from inside the process,
just before a swap, which is also stronger evidence (no window manager in the way): wrap
`glfw.swap_buffers`, and on the chosen frame read the back buffer with `glReadPixels`.

- **Read the LAST of N frames, not the first.** imgui hides a new window for its auto-fit
  frame, so a frame-1 capture never shows a control panel.
- Keep N small (≈3): under Xvfb a swap takes seconds.

## 4. Comparing a port to its C++ original

Correctness is a **C++-vs-Python comparison**. The C++ tree builds and runs headless here with
no patches (it uses gl3w and the system glfw3): `make build-c` configures and builds the
examples into `/opt/rb9-build/bin`, and they load media by the cwd-relative `"media/..."` path,
so run each from `bin/`. Capture the C++ the same way (an `LD_PRELOAD` shim interposing
`glfwSwapBuffers` reads the viewport into a PPM), keep the frame count small, and compare colour
counts and sizes. The captures are triage — animation phase differs between two captures, so a
difference is a lead, not a verdict. The cheapest correctness probe is to **flip one suspected
thing in a scratch copy and watch the picture change** (how the texture-row-order and
sampler-state findings in `fidelity-audit.md` were pinned).

## 5. Capture timing for the heavy demos

Compute-heavy demos take longer than a fixed-geometry one: **12-particlesimulator** allocates
its default 8.4M particles (override with `REDBOOK9_PARTICLE_GROUPS=512` for ~2M), and the
chapter 11/12 compute/image-store demos dispatch real work. Re-run a slow one with a 120 s+
budget before calling it BLANK, and remember llvmpipe (the software rasterizer a no-GPU box
falls back to) is far slower than the maintainer's radeonsi.

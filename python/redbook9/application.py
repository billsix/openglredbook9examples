"""Python port of the ``VermilionApplication`` framework from Red Book 9e.

The C++ side (``include/vapp.h``) declares a base class with
overridable virtuals: ``initialize(title)`` / ``display(auto_redraw)`` /
``resize(w, h)`` / ``on_key(key, scancode, action, mods)`` /
``on_char(codepoint)`` / ``finalize()`` and a ``main_loop`` driver. Each
demo subclasses with ``BEGIN_APP_DECLARATION(MyDemo)`` and registers
itself with ``DEFINE_APP(MyDemo, "title")``.

This module is the same shape in Python:

  - ``Application``     — base class with overridable lifecycle methods
                          and input callbacks
  - ``run(cls, title)`` — entry point; the equivalent of
                          ``DEFINE_APP(cls, title) + main()``

Internally it uses **glfw** for windowing and **imgui_bundle** for the
File→Quit / View→Fullscreen menubar (the mvp convention shared with v7).
A demo never imports glfw itself; key codes live as
``Application.KEY_*`` constants.

A typical demo reads as::

    class MyDemo(application.Application):
        def initialize(self, title):
            super().initialize(title)
            self.program = common.compile_program(vs=VS, fs=FS)
            self.vao = GL.glGenVertexArrays(1)
            GL.glBindVertexArray(self.vao)

        def display(self, auto_redraw=True):
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            GL.glUseProgram(self.program)
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
            super().display(auto_redraw)

    if __name__ == "__main__":
        application.run(MyDemo, "My Demo")
"""

from __future__ import annotations

import sys
import time
from typing import Any, Callable, Optional

# Work around the Mesa/Wayland PyOpenGL+imgui_bundle crash. Symptom:
# ``imgui_bundle``'s GlfwRenderer.__init__ calls ``glVertexAttribPointer``
# which calls ``contextdata.setValue`` which calls ``getContext`` →
# ``OpenGL.platform.GetCurrentContext()`` returning 0/None on this
# combo, even when GLFW has made the context current. Then
# ``getContext`` raises ``Attempt to retrieve context when no valid
# context``. Confirmed by Bill on Fedora 44 + Mesa 26 + AMD radeonsi.
#
# The v7 port worked around this with ``OpenGL.STORE_POINTERS = False``,
# but a recent PyOpenGL release silently ignores that flag with a
# warning unless ``ERROR_ON_COPY = True`` is also set; turning
# ERROR_ON_COPY on would error every ``glUniform3fv(..., [a,b,c])``
# call site (~80+ of them across the port). Instead, monkey-patch
# ``contextdata.getContext`` to return a constant non-None bucket id.
# That makes the per-context bookkeeping degenerate to "one global
# table per process", which is fine because (a) we only ever have one
# GLFW window, and (b) buffers passed to GL are also referenced by
# instance attributes so the contextdata table is functionally
# redundant. Must run BEFORE importing ``OpenGL.GL``.
import OpenGL.contextdata as _contextdata  # noqa: E402


# Deliberately unannotated: PyOpenGL passes an opaque context token
# (or nothing); any concrete annotation here would be wrong-ish.
def _stable_get_context(context=None):
    return context if context is not None else 1


# Deliberate monkey-patch (the Mesa/Wayland workaround documented
# above); ty rightly flags replacing a library function.
_contextdata.getContext = _stable_get_context  # ty: ignore[invalid-assignment]

import glfw  # noqa: E402
import OpenGL.GL as GL  # noqa: E402
from imgui_bundle import imgui  # noqa: E402

from . import window  # noqa: E402  (after the GL-setup patch above)

# The vendored window/menubar/camera helpers (window.py) are imported
# above, after the GL-setup patch.


class Application:
    """Base class for OpenGL Red Book 9e Python demos.

    Override the lifecycle hooks (``initialize``, ``display``,
    ``resize``, ``finalize``) and input callbacks (``on_key``,
    ``on_char``) the same way you'd override the virtuals on
    ``VermilionApplication`` in C++.

    The instance attributes available inside those methods:

      - ``self.window``  — GLFW window handle (set after ``initialize``)
      - ``self.imgui_impl`` — imgui_bundle GlfwRenderer
      - ``self.win_state``  — ``window.WindowState`` for the menubar
      - ``self.window_width`` / ``self.window_height`` — current size

    Notes:
      - GL context defaults to 4.3 core (covers compute / tessellation /
        every other Red Book 9e feature). Override
        ``self.gl_major`` / ``self.gl_minor`` in your subclass before
        calling ``initialize`` if you need something else.
      - ``app_time()`` returns milliseconds since ``initialize`` ran,
        matching the C++ ``app_time()`` semantics.
    """

    # Re-export GLFW key codes as class attributes.
    KEY_ESCAPE = glfw.KEY_ESCAPE
    KEY_SPACE = glfw.KEY_SPACE
    KEY_ENTER = glfw.KEY_ENTER
    KEY_M = glfw.KEY_M
    KEY_R = glfw.KEY_R
    KEY_LEFT = glfw.KEY_LEFT
    KEY_RIGHT = glfw.KEY_RIGHT
    KEY_UP = glfw.KEY_UP
    KEY_DOWN = glfw.KEY_DOWN
    PRESS = glfw.PRESS
    RELEASE = glfw.RELEASE
    REPEAT = glfw.REPEAT

    # Override these in a subclass *before* initialize() if you need
    # a different GL version. 4.3 covers everything the Red Book 9e
    # uses (compute shaders are 4.3+).
    gl_major: int = 4
    gl_minor: int = 3
    samples: int = 0
    initial_width: int = 800
    initial_height: int = 600

    def __init__(self) -> None:
        # ``Any`` is the mvp-sanctioned type for glfw window handles:
        # glfw's stubs type them as an opaque LP__GLFWwindow pointer
        # that nothing else can be annotated with.
        self.window: Any = None
        self.imgui_impl = None
        self.win_state = window.WindowState()
        self.window_width = self.initial_width
        self.window_height = self.initial_height
        self._app_start = 0.0
        self._default_vao = 0  # see _make_default_vao below

    # -- Lifecycle hooks (override these) -----------------------------

    def initialize(self, title: str | None = None) -> None:
        """Called once after the GL context is current. The base class
        implementation only records the start time — every demo's
        override calls ``super().initialize(title)`` first and then
        does its own GL setup, mirroring the C++ ``base::initialize``
        idiom."""
        self._app_start = time.monotonic()
        if title is not None and self.window is not None:
            glfw.set_window_title(window=self.window, title=title)

    def display(self, auto_redraw: bool = True) -> None:
        """Called every frame. The base class swaps buffers — demos
        should call ``super().display(auto_redraw)`` at the end of
        their override, just like C++ does ``base::display(...)``.

        ``auto_redraw`` is the C++ default-arg parameter; we honor it
        for parity but the GLFW main loop always swaps."""
        # No-op here — actual buffer swap happens in main_loop, *after*
        # imgui's own draw, so imgui menus appear over the demo.

    def finalize(self) -> None:
        """Called once after the main loop exits. Free GL resources."""

    def resize(self, width: int, height: int) -> None:
        """``width``/``height`` are FRAMEBUFFER PIXELS, not screen units
        (see _wire_callbacks). Any gl_FragCoord-sized FBO or image
        target a demo allocates must use these, not window units."""
        self.window_width = width
        self.window_height = height
        GL.glViewport(0, 0, max(1, width), max(1, height))

    def on_key(self, key: int, scancode: int, action: int, mods: int) -> None:
        """``key`` is a GLFW key code (use ``Application.KEY_*``).
        Default behavior: ESC closes the window, matching the C++
        framework's behavior."""
        if action == glfw.PRESS and key == glfw.KEY_ESCAPE:
            glfw.set_window_should_close(window=self.window, value=True)

    def on_char(self, codepoint: int) -> None:
        pass

    # -- Helpers a demo can call --------------------------------------

    def app_time(self) -> int:
        """Milliseconds since ``initialize`` was called. Matches the
        C++ ``app_time()`` return type (``unsigned int`` ms)."""
        return int((time.monotonic() - self._app_start) * 1000.0)

    # Note: there is *no* base-class ``aspect`` attribute. C++'s vapp.h
    # doesn't define one either; demos manage their own and use either
    # ``height/width`` or ``width/height`` depending on what their
    # projection helper expects. Don't add one back.

    # -- Main loop (don't override unless you know why) ---------------

    def main_loop(self) -> None:
        """The driver. Equivalent of the inlined ``do { Display();
        glfwPollEvents(); } while (...)`` in vapp.h's ``DEFINE_APP``."""
        while not glfw.window_should_close(self.window):
            # imgui_impl is None only before run() calls init_imgui;
            # main_loop always runs after that, so it is set here.
            self.imgui_impl.process_inputs()  # ty: ignore[unresolved-attribute]
            imgui.new_frame()
            window.draw_menubar(
                self.window, self.win_state, controls=self._controls_hook()
            )

            self.display(auto_redraw=True)

            # Note: do NOT call glUseProgram(0) here. Several
            # redbook9 demos (notably 09-simpletess and 09-teapot)
            # follow C++'s "bind program once in Initialize, never
            # rebind" pattern and break if the program is unbound
            # between frames (glUniformMatrix4fv → INVALID_OPERATION).
            # The hot-reload-safety reason for the original glUseProgram(0)
            # doesn't apply: no redbook9 demo deletes a currently-bound
            # program.
            imgui.render()
            # Same as process_inputs above: set before main_loop runs.
            self.imgui_impl.render(imgui.get_draw_data())  # ty: ignore[unresolved-attribute]
            glfw.swap_buffers(self.window)
            glfw.poll_events()

    # -- Controls menu (rules §3: every C++ control is a widget) --------

    def draw_controls(self) -> None:
        """The body of the menubar's Controls menu: the demo's widgets
        (the C++'s keys as checkboxes, sliders and buttons). Override
        it; ``main_loop`` adds a Controls menu only when a demo does.
        imgui runs a menu body only while the menu is open, so apply a
        widget's change on the spot or store it where ``display`` reads
        it, never rely on this running every frame. ``MVP_CONTROLS_WINDOW``
        (the gates' hook) also draws it in a plain window every frame."""

    def _controls_hook(self) -> Optional[Callable[[], None]]:
        if type(self).draw_controls is Application.draw_controls:
            return None
        return self.draw_controls

    # -- Internal -----------------------------------------------------

    def _make_default_vao(self) -> None:
        """macOS Core Profile prohibits VAO 0. Generate one VAO and
        leave it bound for the lifetime of the demo. Demos that create
        their own VAOs will rebind theirs as needed; what matters is
        that we never have *zero* VAO bound on macOS. Verified working
        for the v4/v7 ports."""
        self._default_vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self._default_vao)

    def _wire_callbacks(self) -> None:
        # Called after init_imgui, so these replace imgui_bundle's own
        # GLFW callbacks; each forwards to imgui's handler first (where
        # the renderer has one) so widgets keep their keyboard and text
        # input, then runs the demo's hook.
        impl: Any = self.imgui_impl

        # (imgui's own resize hook is a *window*-size callback, which this
        # framebuffer-size callback does not replace, so nothing to forward.)
        def _resize(w_: Any, w: int, h: int) -> None:
            self.resize(w, h)

        def _key(w_: Any, k: int, sc: int, act: int, mods: int) -> None:
            if hasattr(impl, "keyboard_callback"):
                impl.keyboard_callback(w_, k, sc, act, mods)
            self.on_key(k, sc, act, mods)

        def _char(w_: Any, cp: int) -> None:
            if hasattr(impl, "char_callback"):
                impl.char_callback(w_, cp)
            self.on_char(cp)

        # Framebuffer-size callback, NOT window-size: the window-size
        # callback delivers screen coordinates, which under HiDPI /
        # fractional scaling are smaller than the framebuffer, so
        # glViewport fed with them draws the scene into the bottom-left
        # fraction of the window with black bars. v7's _sb7.py got this
        # fix on 2026-07-30 (tasks/v7-framework-hidpi-viewport.md); this
        # tree had only the one-time seed in run() and reintroduced the
        # bug on every resize. Aligned 2026-09-09.
        glfw.set_framebuffer_size_callback(window=self.window, cbfun=_resize)
        glfw.set_key_callback(window=self.window, cbfun=_key)
        glfw.set_char_callback(window=self.window, cbfun=_char)


def run(cls: type, title: str = "OpenGL Red Book 9e") -> None:
    """Entry point. Equivalent of ``DEFINE_APP(cls, title)`` plus
    ``main()`` in C++::

        if __name__ == "__main__":
            application.run(MyDemo, "My Demo")

    Performs the GLFW init / window / context dance, then calls the
    demo's ``initialize`` / ``resize`` / loop / ``finalize``."""
    if not glfw.init():
        print("Failed to initialize GLFW", file=sys.stderr)  # noqa: T201
        return

    app = cls()
    try:
        # Open at the C++'s window size: ``vermilion.cpp``'s ``Initialize``
        # creates an 800x600 window for every demo, and the NDC demos, the
        # fixed-horizontal-FOV frustums and the ``gl_FragCoord`` /
        # ``textureSize`` tilings all draw a different picture at any other
        # size. A demo that needs another size sets ``initial_width`` /
        # ``initial_height`` on its class.
        w, h = app.window_width, app.window_height

        glfw.window_hint(hint=glfw.CONTEXT_VERSION_MAJOR, value=app.gl_major)
        glfw.window_hint(hint=glfw.CONTEXT_VERSION_MINOR, value=app.gl_minor)
        glfw.window_hint(
            hint=glfw.OPENGL_PROFILE, value=glfw.OPENGL_CORE_PROFILE
        )
        # glfw's stub wants an int; GL.GL_TRUE is a PyOpenGL Constant
        # (an int subclass at runtime).
        glfw.window_hint(hint=glfw.OPENGL_FORWARD_COMPAT, value=GL.GL_TRUE)  # ty: ignore[invalid-argument-type]
        glfw.window_hint(hint=glfw.SAMPLES, value=app.samples)

        app.window = glfw.create_window(
            width=w, height=h, title=title, monitor=None, share=None
        )
        if not app.window:
            print("Failed to open window", file=sys.stderr)  # noqa: T201
            return
        glfw.make_context_current(app.window)
        glfw.swap_interval(1)

        # Force PyOpenGL to see at least one GL call after
        # make_context_current, before init_imgui — without this its
        # context detection can fail on some Mesa configs (lesson from
        # the v7 port).
        print(f"VENDOR:   {GL.glGetString(GL.GL_VENDOR).decode()}")  # noqa: T201
        print(f"VERSION:  {GL.glGetString(GL.GL_VERSION).decode()}")  # noqa: T201
        print(f"RENDERER: {GL.glGetString(GL.GL_RENDERER).decode()}")  # noqa: T201

        app.imgui_impl = window.init_imgui(app.window)
        # AFTER init_imgui: GlfwRenderer installs its own GLFW key/char/
        # size callbacks and does not chain, so callbacks set before it
        # die silently (tasks/reference/gl-and-imgui-gotchas.md §1 — it
        # took out every key in 18 v4 ports once). Ours forward to imgui's.
        app._wire_callbacks()

        # Set up the always-bound default VAO before the demo runs.
        app._make_default_vao()

        app.initialize(title)
        # Issue an initial resize so the demo's ``aspect`` and viewport
        # match the actual framebuffer size before the first frame.
        fb_w, fb_h = glfw.get_framebuffer_size(app.window)
        app.resize(fb_w, fb_h)

        app.main_loop()

        app.finalize()
    finally:
        if app.imgui_impl is not None:
            app.imgui_impl.shutdown()
        if app.window is not None:
            glfw.destroy_window(app.window)
        glfw.terminate()

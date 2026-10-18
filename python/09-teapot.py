"""09-teapot — Utah teapot via 32 cubic Bezier patches + tessellation.

Port of ``src/09-teapot/09-teapot.cpp``. The 306 control
points and 32 patches are ``Shapes/Teapot.h``'s tables, inlined in
``teapot.py`` (``teapot.load`` returns them). The C++ draws only 306 of
the 512 patch indices (``NumTeapotVertices`` where it means
``NumTeapotIndices``), i.e. 19 of the 32 patches; the port draws the
whole teapot -- a deliberate deviation from an upstream bug.

Keys:
  * I / K — ``Inner`` tessellation level up / down
  * O / L — ``Outer`` tessellation level up / down
  * R     — reset both to 1
  * M     — toggle wireframe / fill
"""

import ctypes
from typing import override

# glfw before imgui_bundle: pyglfw must bind the system GLFW, not the
# X11-only copy imgui_bundle bundles (gl-and-imgui-gotchas.md §1).
import glfw  # noqa: F401
import numpy as np
import OpenGL.GL as GL
from imgui_bundle import imgui

from redbook9 import application, common, teapot, vmath

KEY_I: int = 73
KEY_K: int = 75
KEY_L: int = 76
KEY_O: int = 79
KEY_R: int = 82


class TeapotExample(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        self.inner = 10.0
        self.outer = 10.0
        self._mode: common.GLenum = GL.GL_FILL

        vertices, indices = teapot.load()

        self.vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)

        self.vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=vertices.nbytes,
            data=vertices,
            usage=GL.GL_STATIC_DRAW,
        )

        self.ebo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        GL.glBufferData(
            target=GL.GL_ELEMENT_ARRAY_BUFFER,
            size=indices.nbytes,
            data=indices,
            usage=GL.GL_STATIC_DRAW,
        )
        self.num_indices = indices.size

        self.program: int = common.compile_program_from_files(
            vs=common.media_path("shaders", "teapot", "teapot.vert"),
            tcs=common.media_path("shaders", "teapot", "teapot.cont"),
            tes=common.media_path("shaders", "teapot", "teapot.eval"),
            fs=common.media_path("shaders", "teapot", "teapot.frag"),
        )
        GL.glUseProgram(self.program)

        v_pos: int = GL.glGetAttribLocation(
            program=self.program, name="vPosition"
        )
        GL.glEnableVertexAttribArray(v_pos)
        GL.glVertexAttribPointer(
            index=v_pos,
            size=3,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )

        self.p_loc: int = GL.glGetUniformLocation(
            program=self.program, name="P"
        )
        self.inner_loc: int = GL.glGetUniformLocation(
            program=self.program, name="Inner"
        )
        self.outer_loc: int = GL.glGetUniformLocation(
            program=self.program, name="Outer"
        )
        GL.glUniform1f(self.inner_loc, self.inner)
        GL.glUniform1f(self.outer_loc, self.outer)

        modelview: np.ndarray = vmath.translate(
            x=-0.2625, y=-1.575, z=-1.0
        ) @ vmath.translate(x=0.0, y=0.0, z=-7.5)
        vmath.upload(
            location=GL.glGetUniformLocation(program=self.program, name="MV"),
            mat=modelview,
        )

        GL.glPatchParameteri(GL.GL_PATCH_VERTICES, 16)
        GL.glClearColor(0.0, 0.0, 0.0, 1.0)

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.aspect = float(width) / float(max(1, height))

    @override
    def display(self, auto_redraw: bool = True) -> None:

        # mat.h's Perspective, not vmath.h's: see vmath.perspective_mat_h.
        proj: np.ndarray = vmath.perspective_mat_h(
            fovy_degrees=60.0, aspect=self.aspect, near=5.0, far=10.0
        )
        vmath.upload(location=self.p_loc, mat=proj)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glDrawElements(
            GL.GL_PATCHES,
            self.num_indices,
            GL.GL_UNSIGNED_INT,
            ctypes.c_void_p(0),
        )
        super().display(auto_redraw)

    @override
    def draw_controls(self) -> None:
        # The C++'s I/K, O/L, R and M keys as widgets (rules §3); the keys
        # stay as accelerators. The program is bound once in initialize and
        # never rebound (the C++ idiom), so the uniform sets land in it.
        changed_inner, inner = imgui.slider_float(
            label="Inner (I/K)",
            v=self.inner,
            v_min=1.0,
            v_max=64.0,
            format="%.0f",
        )
        changed_outer, outer = imgui.slider_float(
            label="Outer (O/L)",
            v=self.outer,
            v_min=1.0,
            v_max=64.0,
            format="%.0f",
        )
        if imgui.button("Reset to 1 (R)"):
            inner, outer = 1.0, 1.0
            changed_inner = changed_outer = True
        changed_mode, wire = imgui.checkbox(
            label="Wireframe (M)", v=self._mode == GL.GL_LINE
        )
        if changed_inner:
            self.inner = float(round(inner))
            GL.glUniform1f(self.inner_loc, self.inner)
        if changed_outer:
            self.outer = float(round(outer))
            GL.glUniform1f(self.outer_loc, self.outer)
        if changed_mode:
            self._mode = GL.GL_LINE if wire else GL.GL_FILL
            GL.glPolygonMode(GL.GL_FRONT_AND_BACK, self._mode)

    @override
    def on_key(self, key: int, scancode: int, action: int, mods: int) -> None:
        if action != self.PRESS:
            super().on_key(key, scancode, action, mods)
            return
        if key == KEY_K:
            self.inner = max(1.0, self.inner - 1)
            GL.glUniform1f(self.inner_loc, self.inner)
            return
        if key == KEY_I:
            self.inner = min(64.0, self.inner + 1)
            GL.glUniform1f(self.inner_loc, self.inner)
            return
        if key == KEY_L:
            self.outer = max(1.0, self.outer - 1)
            GL.glUniform1f(self.outer_loc, self.outer)
            return
        if key == KEY_O:
            self.outer = min(64.0, self.outer + 1)
            GL.glUniform1f(self.outer_loc, self.outer)
            return
        if key == KEY_R:
            self.inner = self.outer = 1.0
            GL.glUniform1f(self.inner_loc, self.inner)
            GL.glUniform1f(self.outer_loc, self.outer)
            return
        if key == self.KEY_M:
            self._mode = GL.GL_LINE if self._mode == GL.GL_FILL else GL.GL_FILL
            GL.glPolygonMode(GL.GL_FRONT_AND_BACK, self._mode)
            return
        super().on_key(key, scancode, action, mods)

    @override
    def finalize(self) -> None:
        GL.glDeleteBuffers(1, [self.vbo])
        GL.glDeleteBuffers(1, [self.ebo])
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteProgram(self.program)


if __name__ == "__main__":
    application.run(cls=TeapotExample, title="Teapot Rendering")

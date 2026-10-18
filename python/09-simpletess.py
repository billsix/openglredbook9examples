"""09-simpletess — single 4-vertex patch tessellated by the GPU.

Port of ``src/09-simpletess/09-simpletess.cpp``. Sets
``gl_TessLevelInner`` to 8 and ``gl_TessLevelOuter`` to 4 in the
control shader, evaluates a 2D bilinear quad in the eval shader, then
displaces ``z`` by a Hanning function.

Note: the C++ ``Translate(...) * RotateX(-50)`` and ``Perspective``
helpers come from a row-major ``mat`` lib that uploads with
``GL_TRUE`` (transpose). We use ``vmath`` which does the same.
"""

import ctypes
from typing import override

# glfw before imgui_bundle: pyglfw must bind the system GLFW, not the
# X11-only copy imgui_bundle bundles (gl-and-imgui-gotchas.md §1).
import glfw  # noqa: F401
import numpy as np
import OpenGL.GL as GL
from imgui_bundle import imgui

from redbook9 import application, common, vmath

Z_NEAR: float = 1.0
Z_FAR: float = 3.0
NUM_VERTICES: int = 4


class SimpleTess(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        self._mode: common.GLenum = GL.GL_FILL

        vertices: np.ndarray = np.array(
            [
                [-0.5, -0.5],
                [0.5, -0.5],
                [0.5, 0.5],
                [-0.5, 0.5],
            ],
            dtype=np.float32,
        )

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

        self.program: int = common.compile_program_from_files(
            vs=common.media_path("shaders", "simpletess", "simple.vert"),
            tcs=common.media_path("shaders", "simpletess", "simple.cont"),
            tes=common.media_path("shaders", "simpletess", "simple.eval"),
            fs=common.media_path("shaders", "simpletess", "simple.frag"),
        )
        GL.glUseProgram(self.program)

        v_pos: int = GL.glGetAttribLocation(
            program=self.program, name="vPosition"
        )
        GL.glEnableVertexAttribArray(v_pos)
        GL.glVertexAttribPointer(
            index=v_pos,
            size=2,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )

        self.p_loc: int = GL.glGetUniformLocation(
            program=self.program, name="P"
        )

        modelview: np.ndarray = vmath.translate(
            x=0.0, y=0.0, z=-0.5 * (Z_NEAR + Z_FAR)
        ) @ vmath.rotate(angle_degrees=-50.0, ax=1, ay=0, az=0)
        vmath.upload(
            location=GL.glGetUniformLocation(program=self.program, name="MV"),
            mat=modelview,
        )

        GL.glPatchParameteri(GL.GL_PATCH_VERTICES, 4)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glClearColor(0.0, 0.0, 0.0, 1.0)

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.aspect = float(width) / float(max(1, height))

    @override
    def display(self, auto_redraw: bool = True) -> None:

        # mat.h's Perspective, not vmath.h's: see vmath.perspective_mat_h.
        proj: np.ndarray = vmath.perspective_mat_h(
            fovy_degrees=60.0, aspect=self.aspect, near=Z_NEAR, far=Z_FAR
        )
        vmath.upload(location=self.p_loc, mat=proj)

        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glDrawArrays(GL.GL_PATCHES, 0, NUM_VERTICES)
        super().display(auto_redraw)

    @override
    def draw_controls(self) -> None:
        # The C++'s M key as a widget (rules §3); M stays as the accelerator.
        changed, wire = imgui.checkbox(
            label="Wireframe (M)", v=self._mode == GL.GL_LINE
        )
        if changed:
            self._mode = GL.GL_LINE if wire else GL.GL_FILL
            GL.glPolygonMode(GL.GL_FRONT_AND_BACK, self._mode)

    @override
    def on_key(self, key: int, scancode: int, action: int, mods: int) -> None:
        if action == self.PRESS and key == self.KEY_M:
            self._mode = GL.GL_LINE if self._mode == GL.GL_FILL else GL.GL_FILL
            GL.glPolygonMode(GL.GL_FRONT_AND_BACK, self._mode)
            return
        super().on_key(key, scancode, action, mods)

    @override
    def finalize(self) -> None:
        GL.glDeleteBuffers(1, [self.vbo])
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteProgram(self.program)


if __name__ == "__main__":
    application.run(cls=SimpleTess, title="Tessellation Example")

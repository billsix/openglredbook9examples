"""03-primitiverestart — one draw call covers two triangle strips.

Port of ``src/03-primitiverestart/03-primitiverestart.cpp``.
The 8 cube corners are connected by two triangle strips. Without
primitive restart you'd need two draw commands; with primitive restart,
one ``glDrawElements`` is enough — the index 0xFFFF acts as a
"start over" sentinel.

The C++ defines ``USE_PRIMITIVE_RESTART`` to 1 (use one draw call). We
expose it as ``self.use_primitive_restart`` so it can be toggled at
runtime — mvp ports prefer imgui controls to recompiles
(``feedback_imgui_primary_controls``).
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


class PrimitiveRestartExample(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        self.use_primitive_restart = True

        self.render_prog: int = common.compile_program_from_files(
            vs=common.media_path(
                "shaders", "primitive_restart", "primitive_restart.vs.glsl"
            ),
            fs=common.media_path(
                "shaders", "primitive_restart", "primitive_restart.fs.glsl"
            ),
        )
        GL.glUseProgram(self.render_prog)
        self.model_loc: int = GL.glGetUniformLocation(
            program=self.render_prog, name="model_matrix"
        )
        self.proj_loc: int = GL.glGetUniformLocation(
            program=self.render_prog, name="projection_matrix"
        )

        cube_positions: np.ndarray = np.array(
            [
                [-1.0, -1.0, -1.0, 1.0],
                [-1.0, -1.0, 1.0, 1.0],
                [-1.0, 1.0, -1.0, 1.0],
                [-1.0, 1.0, 1.0, 1.0],
                [1.0, -1.0, -1.0, 1.0],
                [1.0, -1.0, 1.0, 1.0],
                [1.0, 1.0, -1.0, 1.0],
                [1.0, 1.0, 1.0, 1.0],
            ],
            dtype=np.float32,
        )

        cube_colors: np.ndarray = np.array(
            [
                [1.0, 1.0, 1.0, 1.0],
                [1.0, 1.0, 0.0, 1.0],
                [1.0, 0.0, 1.0, 1.0],
                [1.0, 0.0, 0.0, 1.0],
                [0.0, 1.0, 1.0, 1.0],
                [0.0, 1.0, 0.0, 1.0],
                [0.0, 0.0, 1.0, 1.0],
                [0.5, 0.5, 0.5, 1.0],
            ],
            dtype=np.float32,
        )

        cube_indices: np.ndarray = np.array(
            [
                0,
                1,
                2,
                3,
                6,
                7,
                4,
                5,
                0xFFFF,
                2,
                6,
                0,
                4,
                1,
                5,
                3,
                7,
            ],
            dtype=np.uint16,
        )

        self.ebo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        GL.glBufferData(
            target=GL.GL_ELEMENT_ARRAY_BUFFER,
            size=cube_indices.nbytes,
            data=cube_indices,
            usage=GL.GL_STATIC_DRAW,
        )

        self.vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)

        self.vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=cube_positions.nbytes + cube_colors.nbytes,
            data=None,
            usage=GL.GL_STATIC_DRAW,
        )
        GL.glBufferSubData(
            target=GL.GL_ARRAY_BUFFER,
            offset=0,
            size=cube_positions.nbytes,
            data=cube_positions,
        )
        GL.glBufferSubData(
            target=GL.GL_ARRAY_BUFFER,
            offset=cube_positions.nbytes,
            size=cube_colors.nbytes,
            data=cube_colors,
        )

        GL.glVertexAttribPointer(
            index=0,
            size=4,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )
        GL.glVertexAttribPointer(
            index=1,
            size=4,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(cube_positions.nbytes),
        )
        GL.glEnableVertexAttribArray(0)
        GL.glEnableVertexAttribArray(1)

        GL.glClearColor(0.0, 0.0, 0.0, 1.0)

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.aspect = float(height) / float(max(1, width))

    @override
    def display(self, auto_redraw: bool = True) -> None:

        t: float = float(self.app_time() & 0x1FFF) / float(0x1FFF)

        GL.glEnable(GL.GL_CULL_FACE)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glUseProgram(self.render_prog)

        model: np.ndarray = (
            vmath.translate(x=0.0, y=0.0, z=-5.0)
            @ vmath.rotate(angle_degrees=t * 360.0, ax=0, ay=1, az=0)
            @ vmath.rotate(angle_degrees=t * 720.0, ax=0, ay=0, az=1)
        )
        proj: np.ndarray = vmath.frustum(
            left=-1.0,
            right=1.0,
            bottom=-self.aspect,
            top=self.aspect,
            near=1.0,
            far=500.0,
        )
        vmath.upload(location=self.model_loc, mat=model)
        vmath.upload(location=self.proj_loc, mat=proj)

        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)

        if self.use_primitive_restart:
            GL.glEnable(GL.GL_PRIMITIVE_RESTART)
            GL.glPrimitiveRestartIndex(0xFFFF)
            GL.glDrawElements(
                GL.GL_TRIANGLE_STRIP,
                17,
                GL.GL_UNSIGNED_SHORT,
                ctypes.c_void_p(0),
            )
        else:
            GL.glDisable(GL.GL_PRIMITIVE_RESTART)
            GL.glDrawElements(
                GL.GL_TRIANGLE_STRIP,
                8,
                GL.GL_UNSIGNED_SHORT,
                ctypes.c_void_p(0),
            )
            GL.glDrawElements(
                GL.GL_TRIANGLE_STRIP,
                8,
                GL.GL_UNSIGNED_SHORT,
                ctypes.c_void_p(9 * 2),
            )

        super().display(auto_redraw)

    @override
    def draw_controls(self) -> None:
        # Imgui control panel
        _, self.use_primitive_restart = imgui.checkbox(
            label="Use GL_PRIMITIVE_RESTART", v=self.use_primitive_restart
        )

    @override
    def finalize(self) -> None:
        GL.glDeleteBuffers(1, [self.vbo])
        GL.glDeleteBuffers(1, [self.ebo])
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteProgram(self.render_prog)


if __name__ == "__main__":
    application.run(
        cls=PrimitiveRestartExample, title="Primitive Restart Example"
    )

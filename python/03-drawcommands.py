"""03-drawcommands — glDrawArrays / glDrawElements / glDrawElementsBaseVertex / glDrawArraysInstanced.

Port of ``src/03-drawcommands/03-drawcommands.cpp``. Renders
the same triangle four times across the screen, each via a different
draw command, to show that all four routes produce the same on-screen
result. Reuses the ``primitive_restart`` shader pair (positions+color
in, color out) — the shader filename mismatch is in the original.

Aspect convention follows the C++: ``aspect = height/width`` (so the
projection's vertical extent is ``2*aspect = 2h/w``). Don't 'fix' it;
it's deliberate so the math matches the textbook.
"""

import ctypes
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, vmath


class DrawCommandsExample(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0  # set by resize before first frame

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

        # A single triangle (4 positions in C++ — last one duplicates
        # the first; same here for parity).
        positions: np.ndarray = np.array(
            [
                [-1.0, -1.0, 0.0, 1.0],
                [1.0, -1.0, 0.0, 1.0],
                [-1.0, 1.0, 0.0, 1.0],
                [-1.0, -1.0, 0.0, 1.0],
            ],
            dtype=np.float32,
        )

        colors: np.ndarray = np.array(
            [
                [1.0, 1.0, 1.0, 1.0],
                [1.0, 1.0, 0.0, 1.0],
                [1.0, 0.0, 1.0, 1.0],
                [0.0, 1.0, 1.0, 1.0],
            ],
            dtype=np.float32,
        )

        # Indices for the triangle strip (a single triangle).
        indices: np.ndarray = np.array([0, 1, 2], dtype=np.uint16)

        self.ebo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        GL.glBufferData(
            target=GL.GL_ELEMENT_ARRAY_BUFFER,
            size=indices.nbytes,
            data=indices,
            usage=GL.GL_STATIC_DRAW,
        )

        self.vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)

        self.vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=positions.nbytes + colors.nbytes,
            data=None,
            usage=GL.GL_STATIC_DRAW,
        )
        GL.glBufferSubData(
            target=GL.GL_ARRAY_BUFFER,
            offset=0,
            size=positions.nbytes,
            data=positions,
        )
        GL.glBufferSubData(
            target=GL.GL_ARRAY_BUFFER,
            offset=positions.nbytes,
            size=colors.nbytes,
            data=colors,
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
            pointer=ctypes.c_void_p(positions.nbytes),
        )
        GL.glEnableVertexAttribArray(0)
        GL.glEnableVertexAttribArray(1)

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.aspect = float(height) / float(max(1, width))

    @override
    def display(self, auto_redraw: bool = True) -> None:
        GL.glEnable(GL.GL_CULL_FACE)
        GL.glDisable(GL.GL_DEPTH_TEST)

        GL.glClearBufferfv(GL.GL_COLOR, 0, [0.0, 0.0, 0.0, 0.0])
        GL.glUseProgram(self.render_prog)

        proj: np.ndarray = vmath.frustum(
            left=-1.0,
            right=1.0,
            bottom=-self.aspect,
            top=self.aspect,
            near=1.0,
            far=500.0,
        )
        vmath.upload(location=self.proj_loc, mat=proj)

        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)

        # Draw Arrays
        vmath.upload(
            location=self.model_loc, mat=vmath.translate(x=-3.0, y=0.0, z=-5.0)
        )
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)

        # DrawElements
        vmath.upload(
            location=self.model_loc, mat=vmath.translate(x=-1.0, y=0.0, z=-5.0)
        )
        GL.glDrawElements(
            GL.GL_TRIANGLES, 3, GL.GL_UNSIGNED_SHORT, ctypes.c_void_p(0)
        )

        # DrawElementsBaseVertex (offsets every index by basevertex=1)
        vmath.upload(
            location=self.model_loc, mat=vmath.translate(x=1.0, y=0.0, z=-5.0)
        )
        GL.glDrawElementsBaseVertex(
            GL.GL_TRIANGLES, 3, GL.GL_UNSIGNED_SHORT, ctypes.c_void_p(0), 1
        )

        # DrawArraysInstanced
        vmath.upload(
            location=self.model_loc, mat=vmath.translate(x=3.0, y=0.0, z=-5.0)
        )
        GL.glDrawArraysInstanced(GL.GL_TRIANGLES, 0, 3, 1)

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteBuffers(1, [self.vbo])
        GL.glDeleteBuffers(1, [self.ebo])
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteProgram(self.render_prog)


if __name__ == "__main__":
    application.run(cls=DrawCommandsExample, title="Drawing Commands Example")

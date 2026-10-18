"""01-triangles — first VBO + first shader.

Port of ``src/01-triangles/01-triangles.cpp``.

Uploads six 2D vertex positions (two triangles), compiles a trivial
position-only vertex shader and a flat-color fragment shader, and
draws them. Loads the GLSL from
``$REDBOOK9_MEDIA/shaders/triangles/triangles.{vert,frag}`` so the
bytes seen by the GPU exactly match what the C++ demo loads.
"""

import ctypes
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common

VPOSITION: int = 0
NUM_VERTICES: int = 6


class Triangles(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)

        vertices: np.ndarray = np.array(
            [
                [-0.90, -0.90],
                [0.85, -0.90],
                [-0.90, 0.85],  # Triangle 1
                [0.90, -0.85],
                [0.90, 0.90],
                [-0.85, 0.90],  # Triangle 2
            ],
            dtype=np.float32,
        )

        self.vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=vertices.nbytes,
            data=vertices,
            usage=GL.GL_STATIC_DRAW,
        )

        # The same files the C++ ShaderInfo table names.
        self.program: int = common.compile_program_from_files(
            vs=common.media_path("shaders", "triangles", "triangles.vert"),
            fs=common.media_path("shaders", "triangles", "triangles.frag"),
        )

        GL.glUseProgram(self.program)
        GL.glVertexAttribPointer(
            index=VPOSITION,
            size=2,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )
        GL.glEnableVertexAttribArray(VPOSITION)

    @override
    def display(self, auto_redraw: bool = True) -> None:
        GL.glClearBufferfv(GL.GL_COLOR, 0, [0.0, 0.0, 0.0, 0.0])

        GL.glBindVertexArray(self.vao)
        GL.glUseProgram(self.program)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, NUM_VERTICES)

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteBuffers(1, [self.vbo])
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteProgram(self.program)


if __name__ == "__main__":
    application.run(cls=Triangles, title="Triangles")

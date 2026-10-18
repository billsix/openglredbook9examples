"""06-statictexture — small CPU-side checkerboard, swizzled to RGBA.

Port of ``src/06-statictexture/06-statictexture.cpp``.

Uploads an 8×8 ``GL_RED`` checkerboard via ``glTexSubImage2D`` and uses
``GL_TEXTURE_SWIZZLE_RGBA`` to splatter the single channel across all
three RGB outputs while forcing ``a=1`` — a way to see swizzles
working without writing a custom fragment shader.
"""

import ctypes
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common

VS_SOURCE: str = """\
#version 330 core

layout (location = 0) in vec2 in_position;
layout (location = 1) in vec2 in_tex_coord;

out vec2 tex_coord;

void main(void)
{
    gl_Position = vec4(in_position, 0.5, 1.0);
    tex_coord = in_tex_coord;
}
"""

FS_SOURCE: str = """\
#version 330 core

in vec2 tex_coord;

layout (location = 0) out vec4 color;

uniform sampler2D tex;

void main(void)
{
    color = texture(tex, tex_coord);
}
"""


class StaticTexture(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        # Quad covering 75% of the screen.
        quad: np.ndarray = np.array(
            [
                0.75,
                -0.75,
                -0.75,
                -0.75,
                -0.75,
                0.75,
                0.75,
                0.75,
                0.0,
                0.0,
                1.0,
                0.0,
                1.0,
                1.0,
                0.0,
                1.0,
            ],
            dtype=np.float32,
        )

        self.vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=quad.nbytes,
            data=quad,
            usage=GL.GL_STATIC_DRAW,
        )

        self.vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        GL.glVertexAttribPointer(
            index=0,
            size=2,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )
        GL.glVertexAttribPointer(
            index=1,
            size=2,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(8 * 4),
        )
        GL.glEnableVertexAttribArray(0)
        GL.glEnableVertexAttribArray(1)

        self.program: int = common.compile_program(vs=VS_SOURCE, fs=FS_SOURCE)

        # 8×8 checkerboard, single byte per pixel.
        texels: np.ndarray = np.array(
            [
                [0xFF, 0x00] * 4,
                [0x00, 0xFF] * 4,
                [0xFF, 0x00] * 4,
                [0x00, 0xFF] * 4,
                [0xFF, 0x00] * 4,
                [0x00, 0xFF] * 4,
                [0xFF, 0x00] * 4,
                [0x00, 0xFF] * 4,
            ],
            dtype=np.uint8,
        )

        self.tex: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.tex)
        GL.glTexStorage2D(GL.GL_TEXTURE_2D, 4, GL.GL_RGBA8, 8, 8)
        GL.glTexSubImage2D(
            GL.GL_TEXTURE_2D,
            0,
            0,
            0,
            8,
            8,
            GL.GL_RED,
            GL.GL_UNSIGNED_BYTE,
            texels,
        )
        # Swizzle the single red channel into rgb, force alpha=1.
        swizzle: np.ndarray = np.array(
            [GL.GL_RED, GL.GL_RED, GL.GL_RED, GL.GL_ONE], dtype=np.int32
        )
        GL.glTexParameteriv(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_SWIZZLE_RGBA, swizzle
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE
        )
        GL.glGenerateMipmap(GL.GL_TEXTURE_2D)

    @override
    def display(self, auto_redraw: bool = True) -> None:
        GL.glClearColor(0.3, 0.3, 0.3, 1.0)
        GL.glClearDepth(1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glUseProgram(self.program)
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLE_FAN, 0, 4)
        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteBuffers(1, [self.vbo])
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteTextures(size=1, array=[self.tex])
        GL.glDeleteProgram(self.program)


if __name__ == "__main__":
    application.run(cls=StaticTexture, title="Simple Static Texture Example")

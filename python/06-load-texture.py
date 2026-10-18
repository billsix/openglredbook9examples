"""06-load-texture — load a DDS file as a 2D texture and display it.

Port of ``src/06-load-texture/06-load-texture.cpp``.

The C++ side calls ``vglLoadTexture("media/test.dds", ...)`` which
decodes the DDS via Vermilion's DXT decompressor. We use PIL's DDS
support and then ``glTexImage2D`` an RGBA blob — same final image, no
texture compression on the GPU. (If a future Bill demo needs to test
the on-GPU compressed-mip path, swap the loader for one that calls
``glCompressedTexImage2D``.)
"""

import ctypes
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, dds

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


class LoadTexture(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0

        # Two attribute streams in one buffer: 4 vec2 positions then
        # 4 vec2 tex_coords (matches the C++ "split-buffer" layout).
        quad: np.ndarray = np.array(
            [
                1.0,
                -1.0,
                -1.0,
                -1.0,
                -1.0,
                1.0,
                1.0,
                1.0,
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

        # vglLoadTexture: the DDS's own rows (top-down) and 10 mip levels,
        # then the one parameter the C++ sets.
        self.tex: int = dds.upload_2d(common.media_path("test.dds"))
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D,
            GL.GL_TEXTURE_MIN_FILTER,
            GL.GL_LINEAR_MIPMAP_LINEAR,
        )

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.aspect = float(height) / float(max(1, width))

    @override
    def display(self, auto_redraw: bool = True) -> None:
        GL.glClearColor(0.0, 1.0, 0.0, 1.0)
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
    application.run(cls=LoadTexture, title="Simple LoadTexture Example")

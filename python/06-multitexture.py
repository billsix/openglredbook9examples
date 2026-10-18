"""06-multitexture — sample two textures in one fragment shader.

Port of ``src/06-multitexture/06-multitexture.cpp``. Two
DDS textures are bound to units 0 and 1, the FS sums both, and the VS
rotates each texture's coordinates by an animated 2x2 rotation matrix
(one direction for each unit).
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

out vec2 tex_coord0;
out vec2 tex_coord1;

uniform float time;

void main(void)
{
    mat2 m = mat2( vec2(cos(time), sin(time)),
                   vec2(-sin(time), cos(time)) );
    gl_Position = vec4(in_position, 0.5, 1.0);
    tex_coord0 = in_tex_coord * m;
    tex_coord1 = in_tex_coord * transpose(m);
}
"""

FS_SOURCE: str = """\
#version 330 core

in vec2 tex_coord0;
in vec2 tex_coord1;

layout (location = 0) out vec4 color;

uniform sampler2D tex1;
uniform sampler2D tex2;

void main(void)
{
    color = texture(tex1, tex_coord0) + texture(tex2, tex_coord1);
}
"""


class MultiTexture(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        # Don't validate the program — Apple's Core Profile complains
        # when two samplers default to the same unit before
        # glUniform1i runs (lesson from
        # ``feedback_macos_glvalidateprogram_samplers``).
        # common.compile_program does not validate, so this is fine.
        self.program: int = common.compile_program(vs=VS_SOURCE, fs=FS_SOURCE)
        GL.glUseProgram(self.program)
        GL.glUniform1i(
            GL.glGetUniformLocation(program=self.program, name="tex1"), 0
        )
        GL.glUniform1i(
            GL.glGetUniformLocation(program=self.program, name="tex2"), 1
        )
        self.time_loc: int = GL.glGetUniformLocation(
            program=self.program, name="time"
        )

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
            pointer=ctypes.c_void_p(32),
        )
        GL.glEnableVertexAttribArray(0)
        GL.glEnableVertexAttribArray(1)

        # vglLoadTexture for both (the DDS's own rows and mip chain); the
        # C++ sets a minification filter on tex1 only and leaves tex2 at
        # the GL default.
        self.tex1: int = dds.upload_2d(common.media_path("test.dds"))
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D,
            GL.GL_TEXTURE_MIN_FILTER,
            GL.GL_LINEAR_MIPMAP_LINEAR,
        )
        self.tex2: int = dds.upload_2d(common.media_path("test3.dds"))

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.aspect = float(height) / float(max(1, width))

    @override
    def display(self, auto_redraw: bool = True) -> None:
        t: float = float(self.app_time() & 0x3FFF) / float(0x3FFF)

        GL.glClearColor(0.0, 1.0, 0.0, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glUseProgram(self.program)
        GL.glUniform1f(self.time_loc, t)

        GL.glBindVertexArray(self.vao)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.tex1)
        GL.glActiveTexture(GL.GL_TEXTURE1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.tex2)
        GL.glDrawArrays(GL.GL_TRIANGLE_FAN, 0, 4)

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteBuffers(1, [self.vbo])
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteTextures(size=1, array=[self.tex1])
        GL.glDeleteTextures(size=1, array=[self.tex2])
        GL.glDeleteProgram(self.program)


if __name__ == "__main__":
    application.run(cls=MultiTexture, title="Simple Multi-Texture Example")

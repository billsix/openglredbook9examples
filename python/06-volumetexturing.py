"""06-volumetexturing — sample a 3D texture from a quad.

Port of ``src/06-volumetexturing/06-volumetexturing.cpp``.
Loads ``cloud.dds`` (a volume DDS) into a ``GL_TEXTURE_3D`` and samples
it with rotated 3D tex coords on a 2D quad. Output is read from the
red channel only and broadcast to RGBA.
"""

import ctypes
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, dds, vmath

VS_SOURCE: str = """\
#version 330 core

layout (location = 0) in vec2 in_position;
layout (location = 1) in vec2 in_tex_coord;

out vec3 tex_coord;

uniform mat4 tc_rotate;

void main(void)
{
    gl_Position = vec4(in_position, 0.5, 1.0);
    tex_coord = (vec4(in_tex_coord, 0.0, 1.0) * tc_rotate).stp;
}
"""

FS_SOURCE: str = """\
#version 330 core

in vec3 tex_coord;

layout (location = 0) out vec4 color;

uniform sampler3D tex;

void main(void)
{
    color = texture(tex, tex_coord).rrrr;
}
"""


class VolumeTexture(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)
        self.program: int = common.compile_program(vs=VS_SOURCE, fs=FS_SOURCE)
        self.tc_rotate_loc: int = GL.glGetUniformLocation(
            program=self.program, name="tc_rotate"
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

        self.tex: int = dds.upload_3d(common.media_path("cloud.dds"))
        GL.glTexParameteri(
            GL.GL_TEXTURE_3D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR
        )

    @override
    def display(self, auto_redraw: bool = True) -> None:
        t: float = float(self.app_time()) / float(0x3FFF)

        GL.glClearColor(0.6, 0.7, 0.9, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glUseProgram(self.program)

        tc: np.ndarray = (
            vmath.rotate(angle_degrees=t * 170.0, ax=1, ay=0, az=0)
            @ vmath.rotate(angle_degrees=t * 137.0, ax=0, ay=1, az=0)
            @ vmath.rotate(angle_degrees=t * 93.0, ax=0, ay=0, az=1)
        )
        vmath.upload(location=self.tc_rotate_loc, mat=tc)

        GL.glBindVertexArray(self.vao)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDrawArrays(GL.GL_TRIANGLE_FAN, 0, 4)
        GL.glDisable(GL.GL_BLEND)

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteBuffers(1, [self.vbo])
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteTextures(size=1, array=[self.tex])
        GL.glDeleteProgram(self.program)


if __name__ == "__main__":
    application.run(cls=VolumeTexture, title="Volume Texture Example")

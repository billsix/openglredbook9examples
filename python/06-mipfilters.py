"""06-mipfilters — same scene as 06-mipmap, but cycles through min-filter modes.

Port of ``src/06-mipfilters/06-mipfilters.cpp``. Each second
of wall-clock time the demo switches the texture's
``GL_TEXTURE_MIN_FILTER`` between
NEAREST_MIPMAP_NEAREST → LINEAR_MIPMAP_NEAREST →
NEAREST_MIPMAP_LINEAR → LINEAR_MIPMAP_LINEAR. Watching the same
plane shows what each mode does to far-away texels.
"""

import ctypes
import math
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, vmath

VS_SOURCE: str = """\
#version 330 core

layout (location = 0) in vec3 in_position;
layout (location = 1) in vec2 in_texcoord;

out vec2 tex_coord;

uniform mat4 tc_rotate;

void main(void)
{
    gl_Position = tc_rotate * vec4(in_position, 1.0);
    tex_coord = in_texcoord;
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


class MipFiltersExample(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        self.program: int = common.compile_program(vs=VS_SOURCE, fs=FS_SOURCE)

        plane_positions: np.ndarray = np.array(
            [
                [-20.0, 0.0, -50.0],
                [-20.0, 0.0, 50.0],
                [20.0, 0.0, -50.0],
                [20.0, 0.0, 50.0],
            ],
            dtype=np.float32,
        )
        plane_texcoords: np.ndarray = np.array(
            [
                [0.0, 0.0],
                [0.0, 1.0],
                [1.0, 0.0],
                [1.0, 1.0],
            ],
            dtype=np.float32,
        )
        plane_indices: np.ndarray = np.array([0, 1, 2, 3], dtype=np.uint16)

        self.vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=plane_positions.nbytes + plane_texcoords.nbytes,
            data=None,
            usage=GL.GL_STATIC_DRAW,
        )
        GL.glBufferSubData(
            target=GL.GL_ARRAY_BUFFER,
            offset=0,
            size=plane_positions.nbytes,
            data=plane_positions,
        )
        GL.glBufferSubData(
            target=GL.GL_ARRAY_BUFFER,
            offset=plane_positions.nbytes,
            size=plane_texcoords.nbytes,
            data=plane_texcoords,
        )

        self.vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        GL.glVertexAttribPointer(
            index=0,
            size=3,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(
            index=1,
            size=2,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(plane_positions.nbytes),
        )
        GL.glEnableVertexAttribArray(1)

        self.ebo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        GL.glBufferData(
            target=GL.GL_ELEMENT_ARRAY_BUFFER,
            size=plane_indices.nbytes,
            data=plane_indices,
            usage=GL.GL_STATIC_DRAW,
        )

        self.skybox_rotate_loc: int = GL.glGetUniformLocation(
            program=self.program, name="tc_rotate"
        )

        self.tex: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.tex)
        GL.glTexStorage2D(GL.GL_TEXTURE_2D, 7, GL.GL_RGBA8, 64, 64)

        # Build a checkerboard-of-shades for each level.
        for i in range(7):
            size = 64 >> i
            data: np.ndarray = np.zeros((size, size, 4), dtype=np.uint8)
            for j in range(size):
                for k in range(size):
                    v = (k ^ (64 - j)) & 0xFF
                    # The C++ multiplies by 0x04040404 → fills R,G,B,A
                    # with the same byte (clamped to 0xFF * 4 = 0x3FC,
                    # truncated to 0xFC).
                    val = (v * 4) & 0xFF
                    data[j, k] = [val, val, val, val]
            GL.glTexSubImage2D(
                GL.GL_TEXTURE_2D,
                i,
                0,
                0,
                size,
                size,
                GL.GL_RGBA,
                GL.GL_UNSIGNED_BYTE,
                data,
            )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST
        )

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.aspect = float(height) / float(max(1, width))

    @override
    def display(self, auto_redraw: bool = True) -> None:
        t: float = float(self.app_time()) / float(0x3FFF)

        GL.glClearColor(0.0, 0.25, 0.3, 1.0)
        GL.glClearDepth(1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int

        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_ALWAYS)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glUseProgram(self.program)

        tc = vmath.translate(x=0.0, y=0.0, z=-60.0) @ vmath.rotate(
            angle_degrees=80.0 * 3.0 * 0.03, ax=1, ay=0, az=0
        )
        tc = (
            vmath.perspective(
                fovy_degrees=35.0,
                aspect=1.0 / max(self.aspect, 1e-6),
                near=0.1,
                far=700.0,
            )
            @ tc
        )
        vmath.upload(location=self.skybox_rotate_loc, mat=tc)

        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)

        # Cycle min-filter through 4 modes.
        cycle: float = math.fmod(t, 1.0)
        if cycle < 0.25:
            min_f = GL.GL_NEAREST_MIPMAP_NEAREST
        elif cycle < 0.5:
            min_f = GL.GL_LINEAR_MIPMAP_NEAREST
        elif cycle < 0.75:
            min_f = GL.GL_NEAREST_MIPMAP_LINEAR
        else:
            min_f = GL.GL_LINEAR_MIPMAP_LINEAR
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, min_f)

        GL.glDrawElements(
            GL.GL_TRIANGLE_STRIP, 4, GL.GL_UNSIGNED_SHORT, ctypes.c_void_p(0)
        )

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteBuffers(1, [self.vbo])
        GL.glDeleteBuffers(1, [self.ebo])
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteTextures(size=1, array=[self.tex])
        GL.glDeleteProgram(self.program)


if __name__ == "__main__":
    application.run(cls=MipFiltersExample, title="Mipmap Filters Example")

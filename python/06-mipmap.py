"""06-mipmap — manually-built mipmap chain with per-level solid colors.

Port of ``src/06-mipmap/06-mipmap.cpp``. Each mip level is
filled with a different RGB color (red, green, blue, yellow, magenta,
cyan, white) so you can *see* which level the GPU is sampling at any
given LOD. ``GL_TEXTURE_LOD_BIAS = 4.5`` forces sampling far down the
chain.

The C++ has a ``Reshape`` typo (it overrides nothing — base class is
``resize``); we use ``resize`` so the projection updates on window
resize.
"""

import ctypes
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


def _solid_level(color_rgba8: int, size: int) -> np.ndarray:
    """64x64 (or smaller) solid block of a single ABGR-packed uint32.
    PIL/GL want bytes in R,G,B,A order; we feed the raw uint32 array
    so the BMP order matches the C++ which packs as 0xAA_RR_GG_BB on
    little-endian → bytes [BB, GG, RR, AA]. We translate to standard
    R,G,B,A by reading the components explicitly."""
    a = (color_rgba8 >> 24) & 0xFF
    r = (color_rgba8 >> 0) & 0xFF
    g = (color_rgba8 >> 8) & 0xFF
    b = (color_rgba8 >> 16) & 0xFF
    arr: np.ndarray = np.zeros((size, size, 4), dtype=np.uint8)
    arr[..., 0] = r
    arr[..., 1] = g
    arr[..., 2] = b
    arr[..., 3] = a
    return arr


class MipmapExample(application.Application):
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

        # Per-level solid colors.
        # The C++ defines them as 0xFF0000FF, 0xFF00FF00, ... using
        # AABBGGRR layout. We unpack and re-pack to RGBA8 explicitly.
        colors: list[int] = [
            0xFF0000FF,
            0xFF00FF00,
            0xFFFF0000,
            0xFF00FFFF,
            0xFFFF00FF,
            0xFFFFFF00,
            0xFFFFFFFF,
        ]

        self.tex: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.tex)
        GL.glTexStorage2D(GL.GL_TEXTURE_2D, 7, GL.GL_RGBA8, 64, 64)
        for i, c in enumerate(colors):
            size = 64 >> i
            data = _solid_level(color_rgba8=c, size=size)
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
        GL.glTexParameterf(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_LOD_BIAS, 4.5)
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D,
            GL.GL_TEXTURE_MIN_FILTER,
            GL.GL_NEAREST_MIPMAP_LINEAR,
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
    application.run(cls=MipmapExample, title="Mipmap Example")

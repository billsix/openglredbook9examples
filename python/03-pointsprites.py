"""03-pointsprites — point sprites textured with a TGA image.

Port of ``src/03-pointsprites/03-pointsprites.cpp``.

Generates 4 random 3D points, draws them as ``GL_POINTS`` with
``GL_PROGRAM_POINT_SIZE`` enabled and a ``gl_PointSize`` written by
the vertex shader. Each fragment samples a TGA texture (sprite2.tga)
using the built-in ``gl_PointCoord``. Additive blending makes the
overlapping sprites brighten.
"""

import ctypes
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, vmath

POINT_COUNT: int = 4


def _xorshift_floats(n: int, seed: int = 0x13371337) -> list[float]:
    """Reproduce the C++ ``random_float()`` deterministic stream so
    the four points land in the same locations as in the C++ demo."""
    out = []
    s = seed
    for _ in range(n):
        s = (s * 16807) & 0xFFFFFFFF
        tmp = (s ^ (s >> 4) ^ ((s << 15) & 0xFFFFFFFF)) & 0xFFFFFFFF
        bits = (tmp >> 9) | 0x3F800000
        # Bitcast to float to match the C++ trick
        f = np.frombuffer(np.uint32(bits).tobytes(), dtype=np.float32)[0]
        out.append(float(f) - 1.0)
    return out


class PointSpriteExample(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0

        self.sprite_texture: int = common.load_texture_2d(
            common.media_path("sprite2.tga")
        )

        self.render_prog: int = common.compile_program_from_files(
            vs=common.media_path(
                "shaders", "pointsprites", "pointsprites.vs.glsl"
            ),
            fs=common.media_path(
                "shaders", "pointsprites", "pointsprites.fs.glsl"
            ),
        )
        GL.glUseProgram(self.render_prog)
        self.model_loc: int = GL.glGetUniformLocation(
            program=self.render_prog, name="model_matrix"
        )
        self.proj_loc: int = GL.glGetUniformLocation(
            program=self.render_prog, name="projection_matrix"
        )

        # Random points reproducing the C++ stream.
        floats = _xorshift_floats(POINT_COUNT * 3)
        positions: np.ndarray = np.zeros((POINT_COUNT, 4), dtype=np.float32)
        for i in range(POINT_COUNT):
            positions[i, 0] = floats[3 * i + 0] * 2.0 - 1.0
            positions[i, 1] = floats[3 * i + 1] * 2.0 - 1.0
            positions[i, 2] = floats[3 * i + 2] * 2.0 - 1.0
            positions[i, 3] = 1.0

        self.vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)

        self.vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=positions.nbytes,
            data=positions,
            usage=GL.GL_STATIC_DRAW,
        )

        GL.glVertexAttribPointer(
            index=0,
            size=4,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )
        GL.glEnableVertexAttribArray(0)

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
        proj: np.ndarray = vmath.frustum(
            left=-1.0,
            right=1.0,
            bottom=-self.aspect,
            top=self.aspect,
            near=1.0,
            far=8.0,
        )
        vmath.upload(location=self.proj_loc, mat=proj)

        GL.glBindTexture(GL.GL_TEXTURE_2D, self.sprite_texture)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE)
        GL.glEnable(GL.GL_PROGRAM_POINT_SIZE)
        GL.glPointSize(32.0)

        model: np.ndarray = (
            vmath.translate(x=0.0, y=0.0, z=-2.0)
            @ vmath.rotate(angle_degrees=t * 360.0, ax=0, ay=1, az=0)
            @ vmath.rotate(angle_degrees=t * 720.0, ax=0, ay=0, az=1)
        )
        vmath.upload(location=self.model_loc, mat=model)

        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_POINTS, 0, POINT_COUNT)

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteBuffers(1, [self.vbo])
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteTextures(size=1, array=[self.sprite_texture])
        GL.glDeleteProgram(self.render_prog)


if __name__ == "__main__":
    application.run(cls=PointSpriteExample, title="Point Sprite Example")

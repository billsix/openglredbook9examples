"""03-instancing — instanced rendering with per-instance attributes.

Port of ``src/03-instancing/03-instancing.cpp``.

Loads ``armadillo_low.vbm``, sets up two instanced vertex attributes
(weights and color) on the model's VAO, then renders 200 copies. The
vertex shader weights an array of 4 model matrices per instance to
produce the swirling motion.
"""

import ctypes
import math
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, vbm, vmath

INSTANCE_COUNT: int = 200


VS_SOURCE: str = """\
#version 410

uniform mat4 model_matrix[4];
uniform mat4 projection_matrix;

layout (location = 0) in vec4 position;
layout (location = 1) in vec3 normal;

layout (location = 3) in vec4 instance_weights;
layout (location = 4) in vec4 instance_color;

out vec3 vs_fs_normal;
out vec4 vs_fs_color;

void main(void)
{
    int n;
    mat4 m = mat4(0.0);
    vec4 pos = position;
    vec4 weights = normalize(instance_weights);
    for (n = 0; n < 4; n++)
    {
        m += (model_matrix[n] * weights[n]);
    }
    vs_fs_normal = normalize((m * vec4(normal, 0.0)).xyz);
    vs_fs_color = instance_color;
    gl_Position = projection_matrix * (m * pos);
}
"""

FS_SOURCE: str = """\
#version 410

layout (location = 0) out vec4 color;

in vec3 vs_fs_normal;
in vec4 vs_fs_color;

void main(void)
{
    color = vs_fs_color * (0.1 + abs(vs_fs_normal.z)) + vec4(0.8, 0.9, 0.7, 1.0) * pow(abs(vs_fs_normal.z), 40.0);
}
"""


class InstancingExample(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0

        self.render_prog: int = common.compile_program(
            vs=VS_SOURCE, fs=FS_SOURCE
        )
        GL.glUseProgram(self.render_prog)
        self.model_loc: int = GL.glGetUniformLocation(
            program=self.render_prog, name="model_matrix"
        )
        self.proj_loc: int = GL.glGetUniformLocation(
            program=self.render_prog, name="projection_matrix"
        )

        # Load the armadillo model.
        self.object = vbm.VBObject()
        self.object.load(
            common.media_path("armadillo_low.vbm"),
            vertex_index=0,
            normal_index=1,
            tex0_index=2,
        )
        self.object.bind_vao()

        # Build colors[] (also used to seed weights initial-data).
        colors: np.ndarray = np.zeros((INSTANCE_COUNT, 4), dtype=np.float32)
        for n in range(INSTANCE_COUNT):
            a = float(n) / 4.0
            b = float(n) / 5.0
            c = float(n) / 6.0
            colors[n, 0] = 0.5 * (math.sin(a + 1.0) + 1.0)
            colors[n, 1] = 0.5 * (math.sin(b + 2.0) + 1.0)
            colors[n, 2] = 0.5 * (math.sin(c + 3.0) + 1.0)
            colors[n, 3] = 1.0

        # Weights VBO (location 3, divisor 1).
        self.weight_vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.weight_vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=colors.nbytes,
            data=colors,
            usage=GL.GL_DYNAMIC_DRAW,
        )
        GL.glVertexAttribDivisor(3, 1)
        GL.glVertexAttribPointer(
            index=3,
            size=4,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )
        GL.glEnableVertexAttribArray(3)

        # Color VBO (location 4, divisor 1).
        self.color_vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.color_vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=colors.nbytes,
            data=colors,
            usage=GL.GL_STATIC_DRAW,
        )
        GL.glVertexAttribDivisor(4, 1)
        GL.glVertexAttribPointer(
            index=4,
            size=4,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )
        GL.glEnableVertexAttribArray(4)

        GL.glBindVertexArray(0)

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.aspect = float(height) / float(max(1, width))

    @override
    def display(self, auto_redraw: bool = True) -> None:
        t: float = float(self.app_time() & 0x3FFFF) / float(0x3FFFF)

        # Update per-instance weights.
        weights: np.ndarray = np.zeros((INSTANCE_COUNT, 4), dtype=np.float32)
        two_pi: float = 6.28318531
        for n in range(INSTANCE_COUNT):
            a = n / 4.0
            b = n / 5.0
            c = n / 6.0
            weights[n, 0] = 0.5 * (math.sin(t * two_pi * 8.0 + a) + 1.0)
            weights[n, 1] = 0.5 * (math.sin(t * two_pi * 26.0 + b) + 1.0)
            weights[n, 2] = 0.5 * (math.sin(t * two_pi * 21.0 + c) + 1.0)
            weights[n, 3] = 0.5 * (math.sin(t * two_pi * 13.0 + a + b) + 1.0)

        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.weight_vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=weights.nbytes,
            data=weights,
            usage=GL.GL_DYNAMIC_DRAW,
        )

        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glEnable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)

        GL.glUseProgram(self.render_prog)

        # Build the four model matrices.
        mats = []
        for n in range(4):
            m: np.ndarray = (
                vmath.scale(5.0)
                @ vmath.rotate(
                    angle_degrees=t * 360.0 * 40.0 + (n + 1) * 29.0,
                    ax=0,
                    ay=1,
                    az=0,
                )
                @ vmath.rotate(
                    angle_degrees=t * 360.0 * 20.0 + (n + 1) * 35.0,
                    ax=0,
                    ay=0,
                    az=1,
                )
                @ vmath.rotate(
                    angle_degrees=t * 360.0 * 30.0 + (n + 1) * 67.0,
                    ax=0,
                    ay=1,
                    az=0,
                )
                @ vmath.translate(x=n * 10.0 - 15.0, y=0.0, z=0.0)
                @ vmath.scale(0.01)
            )
            mats.append(m)
        vmath.upload_array(location=self.model_loc, mats=mats)

        proj: np.ndarray = vmath.frustum(
            left=-1.0,
            right=1.0,
            bottom=-self.aspect,
            top=self.aspect,
            near=1.0,
            far=5000.0,
        ) @ vmath.translate(x=0.0, y=0.0, z=-100.0)
        vmath.upload(location=self.proj_loc, mat=proj)

        self.object.render(0, INSTANCE_COUNT)

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteBuffers(1, [self.weight_vbo])
        GL.glDeleteBuffers(1, [self.color_vbo])
        GL.glDeleteProgram(self.render_prog)
        self.object.free()


if __name__ == "__main__":
    application.run(cls=InstancingExample, title="Instancing Example")

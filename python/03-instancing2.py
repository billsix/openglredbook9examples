"""03-instancing2 — instanced rendering with a per-instance mat4.

Port of ``src/03-instancing2/03-instancing2.cpp``.

Compared to 03-instancing this version puts a full ``mat4 model_matrix``
into the vertex attributes (consuming 4 attribute locations, one per
column) so each instance gets a unique per-vertex transform without
needing an array uniform. Color is also a per-instance attribute.
"""

import ctypes
import math
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, vbm, vmath

INSTANCE_COUNT: int = 100


VS_SOURCE: str = """\
#version 330

// 'position' and 'normal' are regular vertex attributes
layout (location = 0) in vec4 position;
layout (location = 1) in vec3 normal;

// Color is a per-instance attribute
layout (location = 2) in vec4 color;

// model_matrix will be used as a per-instance transformation
// matrix. Note that a mat4 consumes 4 consecutive locations, so
// this will actually sit in locations, 3, 4, 5, and 6.
layout (location = 3) in mat4 model_matrix;

// The view matrix and the projection matrix are constant across a draw
uniform mat4 view_matrix;
uniform mat4 projection_matrix;

// The output of the vertex shader (matched to the fragment shader)
out VERTEX
{
    vec3    normal;
    vec4    color;
} vertex;

// Ok, go!
void main(void)
{
    // Construct a model-view matrix from the uniform view matrix
    // and the per-instance model matrix.
    mat4 model_view_matrix = view_matrix * model_matrix;

    // Transform position by the model-view matrix, then by the
    // projection matrix.
    gl_Position = projection_matrix * (model_view_matrix * position);
    // Transform the normal by the upper-left-3x3-submatrix of the
    // model-view matrix
    vertex.normal = mat3(model_view_matrix) * normal;
    // Pass the per-instance color through to the fragment shader.
    vertex.color = color;
}
"""

FS_SOURCE: str = """\
#version 330

layout (location = 0) out vec4 color;

in VERTEX
{
    vec3    normal;
    vec4    color;
} vertex;

void main(void)
{
    color = vertex.color * (0.1 + abs(vertex.normal.z)) + vec4(0.8, 0.9, 0.7, 1.0) * pow(abs(vertex.normal.z), 40.0);
}
"""


class Instancing2Example(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0

        self.render_prog: int = common.compile_program(
            vs=VS_SOURCE, fs=FS_SOURCE
        )
        GL.glUseProgram(self.render_prog)
        self.view_loc: int = GL.glGetUniformLocation(
            program=self.render_prog, name="view_matrix"
        )
        self.proj_loc: int = GL.glGetUniformLocation(
            program=self.render_prog, name="projection_matrix"
        )

        self.object = vbm.VBObject()
        self.object.load(common.media_path("armadillo_low.vbm"))
        self.object.bind_vao()

        # Color (location 2, divisor 1).
        colors: np.ndarray = np.zeros((INSTANCE_COUNT, 4), dtype=np.float32)
        for n in range(INSTANCE_COUNT):
            colors[n, 0] = 0.5 + 0.25 * (math.sin(n / 4.0 + 1.0) + 1.0)
            colors[n, 1] = 0.5 + 0.25 * (math.sin(n / 5.0 + 2.0) + 1.0)
            colors[n, 2] = 0.5 + 0.25 * (math.sin(n / 6.0 + 3.0) + 1.0)
            colors[n, 3] = 1.0
        self.color_buffer: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.color_buffer)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=colors.nbytes,
            data=colors,
            usage=GL.GL_DYNAMIC_DRAW,
        )
        GL.glVertexAttribPointer(
            index=2,
            size=4,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )
        GL.glEnableVertexAttribArray(2)
        GL.glVertexAttribDivisor(2, 1)

        # Model matrices (locations 3..6, divisor 1, stride 64, offsets 0,16,32,48).
        self.model_matrix_buffer: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.model_matrix_buffer)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=INSTANCE_COUNT * 64,
            data=None,
            usage=GL.GL_DYNAMIC_DRAW,
        )
        for i in range(4):
            GL.glVertexAttribPointer(
                index=3 + i,
                size=4,
                type=GL.GL_FLOAT,
                normalized=GL.GL_FALSE,
                stride=64,
                pointer=ctypes.c_void_p(16 * i),
            )
            GL.glEnableVertexAttribArray(3 + i)
            GL.glVertexAttribDivisor(3 + i, 1)

        GL.glBindVertexArray(0)

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.aspect = float(height) / float(max(1, width))

    @override
    def display(self, auto_redraw: bool = True) -> None:
        t: float = float(self.app_time() & 0x3FFF) / float(0x3FFF)

        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glEnable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)

        # Build per-instance model matrices on the CPU; upload all at
        # once. Equivalent of the C++ glMapBuffer/Unmap dance, but
        # numpy-friendly.
        mats: np.ndarray = np.zeros((INSTANCE_COUNT, 4, 4), dtype=np.float32)
        # GLSL is column-major and the per-instance attribute layout
        # expects 4 columns of 4 floats each. We build numpy
        # row-major then transpose into the buffer.
        for n in range(INSTANCE_COUNT):
            a: float = 50.0 * n / 4.0
            b: float = 50.0 * n / 5.0
            c: float = 50.0 * n / 6.0
            m: np.ndarray = (
                vmath.rotate(angle_degrees=a + t * 360.0, ax=1, ay=0, az=0)
                @ vmath.rotate(angle_degrees=b + t * 360.0, ax=0, ay=1, az=0)
                @ vmath.rotate(angle_degrees=c + t * 360.0, ax=0, ay=0, az=1)
                @ vmath.translate(x=10.0 + a, y=40.0 + b, z=50.0 + c)
            )
            mats[n] = m.T  # transpose into column-major for GLSL
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.model_matrix_buffer)
        GL.glBufferSubData(
            target=GL.GL_ARRAY_BUFFER, offset=0, size=mats.nbytes, data=mats
        )

        GL.glUseProgram(self.render_prog)
        view: np.ndarray = vmath.translate(
            x=0.0, y=0.0, z=-1500.0
        ) @ vmath.rotate(angle_degrees=t * 360.0 * 2.0, ax=0, ay=1, az=0)
        proj: np.ndarray = vmath.frustum(
            left=-1.0,
            right=1.0,
            bottom=-self.aspect,
            top=self.aspect,
            near=1.0,
            far=5000.0,
        )
        vmath.upload(location=self.view_loc, mat=view)
        vmath.upload(location=self.proj_loc, mat=proj)

        self.object.render(0, INSTANCE_COUNT)

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteBuffers(1, [self.color_buffer])
        GL.glDeleteBuffers(1, [self.model_matrix_buffer])
        GL.glDeleteProgram(self.render_prog)
        self.object.free()


if __name__ == "__main__":
    application.run(cls=Instancing2Example, title="Instancing 2 Example")

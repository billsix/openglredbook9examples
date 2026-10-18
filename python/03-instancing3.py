"""03-instancing3 — gl_InstanceID + Texture Buffer Objects.

Port of ``src/03-instancing3/03-instancing3.cpp``.

Uses ``samplerBuffer`` TBOs to provide per-instance colors and a
per-instance ``mat4`` (split into 4 ``vec4`` columns). The vertex
shader fetches by ``gl_InstanceID`` and reassembles the matrix.
"""

import math
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, vbm, vmath

INSTANCE_COUNT: int = 100


VS_SOURCE: str = """\
#version 410

// 'position' and 'normal' are regular vertex attributes
layout (location = 0) in vec4 position;
layout (location = 1) in vec3 normal;

// Color is a per-instance attribute
layout (location = 2) in vec4 color;

// The view matrix and the projection matrix are constant across a draw
uniform mat4 view_matrix;
uniform mat4 projection_matrix;

// These are the TBOs that hold per-instance colors and per-instance
// model matrices
uniform samplerBuffer color_tbo;
uniform samplerBuffer model_matrix_tbo;

// The output of the vertex shader (matched to the fragment shader)
out VERTEX
{
    vec3    normal;
    vec4    color;
} vertex;

// Ok, go!
void main(void)
{
    // Use gl_InstanceID to obtain the instance color from the color TBO
    vec4 color = texelFetch(color_tbo, gl_InstanceID);

    // Generating the model matrix is more complex because you can't
    // store mat4 data in a TBO. Instead, we need to store each matrix
    // as four vec4 variables and assemble the matrix in the shader.
    // First, fetch the four columns of the matrix (remember, matrices are
    // stored in memory in column-primary order).
    vec4 col1 = texelFetch(model_matrix_tbo, gl_InstanceID * 4);
    vec4 col2 = texelFetch(model_matrix_tbo, gl_InstanceID * 4 + 1);
    vec4 col3 = texelFetch(model_matrix_tbo, gl_InstanceID * 4 + 2);
    vec4 col4 = texelFetch(model_matrix_tbo, gl_InstanceID * 4 + 3);

    // Now assemble the four columns into a matrix.
    mat4 model_matrix = mat4(col1, col2, col3, col4);

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
#version 410

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


class InstanceIDExample(application.Application):
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

        # Sampler bindings (TBOs go to texture units 0 and 1).
        GL.glUniform1i(
            GL.glGetUniformLocation(program=self.render_prog, name="color_tbo"),
            0,
        )
        GL.glUniform1i(
            GL.glGetUniformLocation(
                program=self.render_prog, name="model_matrix_tbo"
            ),
            1,
        )

        self.object = vbm.VBObject()
        self.object.load(common.media_path("armadillo_low.vbm"))

        # Color TBO on unit 0.
        colors: np.ndarray = np.zeros((INSTANCE_COUNT, 4), dtype=np.float32)
        for n in range(INSTANCE_COUNT):
            colors[n, 0] = 0.5 + 0.25 * (math.sin(n / 4.0 + 1.0) + 1.0)
            colors[n, 1] = 0.5 + 0.25 * (math.sin(n / 5.0 + 2.0) + 1.0)
            colors[n, 2] = 0.5 + 0.25 * (math.sin(n / 6.0 + 3.0) + 1.0)
            colors[n, 3] = 1.0

        self.color_tbo: int = GL.glGenTextures(1)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_BUFFER, self.color_tbo)
        self.color_buffer: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, self.color_buffer)
        GL.glBufferData(
            target=GL.GL_TEXTURE_BUFFER,
            size=colors.nbytes,
            data=colors,
            usage=GL.GL_STATIC_DRAW,
        )
        GL.glTexBuffer(GL.GL_TEXTURE_BUFFER, GL.GL_RGBA32F, self.color_buffer)

        # Model-matrix TBO on unit 1.
        self.matrix_tbo: int = GL.glGenTextures(1)
        GL.glActiveTexture(GL.GL_TEXTURE1)
        GL.glBindTexture(GL.GL_TEXTURE_BUFFER, self.matrix_tbo)
        self.matrix_buffer: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, self.matrix_buffer)
        GL.glBufferData(
            target=GL.GL_TEXTURE_BUFFER,
            size=INSTANCE_COUNT * 64,
            data=None,
            usage=GL.GL_DYNAMIC_DRAW,
        )
        GL.glTexBuffer(GL.GL_TEXTURE_BUFFER, GL.GL_RGBA32F, self.matrix_buffer)
        GL.glActiveTexture(GL.GL_TEXTURE0)

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.aspect = float(height) / float(max(1, width))

    @override
    def display(self, auto_redraw: bool = True) -> None:
        t: float = float(self.app_time() & 0x3FFF) / float(0x3FFF)

        # Build per-instance matrices (transposed into column-major
        # because the shader reconstructs the matrix from columns).
        mats: np.ndarray = np.zeros((INSTANCE_COUNT, 4, 4), dtype=np.float32)
        for n in range(INSTANCE_COUNT):
            a = 50.0 * n / 4.0
            b = 50.0 * n / 5.0
            c = 50.0 * n / 6.0
            m: np.ndarray = (
                vmath.rotate(angle_degrees=a + t * 360.0, ax=1, ay=0, az=0)
                @ vmath.rotate(angle_degrees=b + t * 360.0, ax=0, ay=1, az=0)
                @ vmath.rotate(angle_degrees=c + t * 360.0, ax=0, ay=0, az=1)
                @ vmath.translate(x=10.0 + a, y=40.0 + b, z=50.0 + c)
            )
            mats[n] = m.T
        GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, self.matrix_buffer)
        GL.glBufferData(
            target=GL.GL_TEXTURE_BUFFER,
            size=mats.nbytes,
            data=mats,
            usage=GL.GL_DYNAMIC_DRAW,
        )

        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glEnable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)

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
        GL.glDeleteBuffers(1, [self.matrix_buffer])
        GL.glDeleteTextures(size=1, array=[self.color_tbo])
        GL.glDeleteTextures(size=1, array=[self.matrix_tbo])
        GL.glDeleteProgram(self.render_prog)
        self.object.free()


if __name__ == "__main__":
    application.run(cls=InstanceIDExample, title="gl_InstanceID Example")

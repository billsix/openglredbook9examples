"""10-draw-xfb — geometry shader sorts triangles into two TF streams,
then ``glDrawTransformFeedbackStream`` redraws each.

Port of ``src/10-draw-xfb/10-draw-xfb.cpp``. The trick:

  1. ``sort_prog`` runs vertex+geometry stages with rasterizer
     discard. The GS computes the input triangle's face normal; if
     ``face_normal.x < 0`` it emits to TF stream 0 (right-facing),
     otherwise stream 1 (left-facing). Each stream is bound to a
     separate VBO.
  2. ``render_prog`` then runs ``glDrawTransformFeedbackStream`` once
     per stream, with a different uniform color, drawing the captured
     vertices as triangles.

Multi-stream TF requires the ``gl_NextBuffer`` token in the varying
list — that's how you tell the linker to bind subsequent varyings to
the next TF buffer.
"""

import ctypes
import math
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, vbm, vmath

SORT_VS: str = """\
#version 410

uniform mat4 model_matrix;

layout (location = 0) in vec4 position;
layout (location = 1) in vec3 normal;

out vec3 vs_normal;

void main(void)
{
    vs_normal = (model_matrix * vec4(normal, 0.0)).xyz;
    gl_Position = model_matrix * position;
}
"""

SORT_GS: str = """\
#version 410

layout (triangles) in;
layout (points, max_vertices = 3) out;

uniform mat4 projection_matrix;

in vec3 vs_normal[];

layout (stream = 0) out vec4 rf_position;
layout (stream = 0) out vec3 rf_normal;

layout (stream = 1) out vec4 lf_position;
layout (stream = 1) out vec3 lf_normal;

void main(void)
{
    vec4 A = gl_in[0].gl_Position;
    vec4 B = gl_in[1].gl_Position;
    vec4 C = gl_in[2].gl_Position;
    vec3 AB = (B - A).xyz;
    vec3 AC = (C - A).xyz;
    vec3 face_normal = cross(AB, AC);
    int i;

    if (face_normal.x < 0.0)
    {
        for (i = 0; i < gl_in.length(); i++)
        {
            rf_position = projection_matrix * (gl_in[i].gl_Position - vec4(30.0, 0.0, 0.0, 0.0));
            rf_normal = vs_normal[i];
            EmitStreamVertex(0);
        }
        EndStreamPrimitive(0);
    }
    else
    {
        for (i = 0; i < gl_in.length(); i++)
        {
            lf_position = projection_matrix * (gl_in[i].gl_Position + vec4(30.0, 0.0, 0.0, 0.0));
            lf_normal = vs_normal[i];
            EmitStreamVertex(1);
        }
        EndStreamPrimitive(1);
    }
}
"""

RENDER_VS: str = """\
#version 410

layout (location = 0) in vec4 position;
layout (location = 1) in vec3 normal;

out vec3 vs_normal;

void main(void)
{
    vs_normal = normal;
    gl_Position = position;
}
"""

RENDER_FS: str = """\
#version 410

layout (location = 0) out vec4 color;

uniform vec4 pass_color;

in vec3 vs_normal;

void main(void)
{
    color = pass_color * (0.2 + pow(abs(vs_normal.z), 4.0)) + vec4(1.0, 1.0, 1.0, 0.0) * pow(abs(vs_normal.z), 37.0);
}
"""


STRIDE: int = 16 + 12  # vec4 position + vec3 normal, interleaved


class DrawXfb(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        self.xfb: int = GL.glGenTransformFeedbacks(1)
        GL.glBindTransformFeedback(GL.GL_TRANSFORM_FEEDBACK, self.xfb)

        self.sort_prog: int = common.compile_program(
            vs=SORT_VS,
            gs=SORT_GS,
            tf_varyings=[
                "rf_position",
                "rf_normal",
                "gl_NextBuffer",
                "lf_position",
                "lf_normal",
            ],
            tf_buffer_mode=GL.GL_INTERLEAVED_ATTRIBS,
        )
        GL.glUseProgram(self.sort_prog)
        self.model_loc: int = GL.glGetUniformLocation(
            program=self.sort_prog, name="model_matrix"
        )
        self.proj_loc: int = GL.glGetUniformLocation(
            program=self.sort_prog, name="projection_matrix"
        )

        self.vao = GL.glGenVertexArrays(2)
        self.vbo = GL.glGenBuffers(2)
        for i in range(2):
            GL.glBindBuffer(GL.GL_TRANSFORM_FEEDBACK_BUFFER, self.vbo[i])
            GL.glBufferData(
                target=GL.GL_TRANSFORM_FEEDBACK_BUFFER,
                size=1024 * 1024 * 4,
                data=None,
                usage=GL.GL_DYNAMIC_COPY,
            )
            GL.glBindBufferBase(GL.GL_TRANSFORM_FEEDBACK_BUFFER, i, self.vbo[i])

            GL.glBindVertexArray(self.vao[i])
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo[i])
            GL.glVertexAttribPointer(
                index=0,
                size=4,
                type=GL.GL_FLOAT,
                normalized=GL.GL_FALSE,
                stride=STRIDE,
                pointer=ctypes.c_void_p(0),
            )
            GL.glVertexAttribPointer(
                index=1,
                size=3,
                type=GL.GL_FLOAT,
                normalized=GL.GL_FALSE,
                stride=STRIDE,
                pointer=ctypes.c_void_p(16),
            )
            GL.glEnableVertexAttribArray(0)
            GL.glEnableVertexAttribArray(1)

        self.render_prog: int = common.compile_program(
            vs=RENDER_VS, fs=RENDER_FS
        )

        self.object = vbm.VBObject()
        self.object.load(common.media_path("ninja.vbm"))

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.aspect = float(height) / float(max(1, width))

    @override
    def display(self, auto_redraw: bool = True) -> None:
        t: float = float(self.app_time() & 0x3FFF) / float(0x3FFF)

        GL.glDisable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)

        GL.glClearColor(0.0, 0.0, 0.0, 1.0)
        GL.glClearDepth(1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int

        GL.glUseProgram(self.sort_prog)

        two_pi: float = 6.28318531
        p: np.ndarray = vmath.frustum(
            left=-1.0,
            right=1.0,
            bottom=self.aspect,
            top=-self.aspect,
            near=1.0,
            far=5000.0,
        )
        m: np.ndarray = (
            vmath.translate(
                x=0.0, y=0.0, z=100.0 * math.sin(two_pi * t) - 230.0
            )
            @ vmath.rotate(angle_degrees=360.0 * t, ax=1, ay=0, az=0)
            @ vmath.rotate(angle_degrees=360.0 * t * 2.0, ax=0, ay=1, az=0)
            @ vmath.rotate(angle_degrees=360.0 * t * 5.0, ax=0, ay=0, az=1)
            @ vmath.translate(x=0.0, y=-80.0, z=0.0)
        )
        vmath.upload(location=self.model_loc, mat=m)
        vmath.upload(location=self.proj_loc, mat=p)

        GL.glEnable(GL.GL_RASTERIZER_DISCARD)
        GL.glBindTransformFeedback(GL.GL_TRANSFORM_FEEDBACK, self.xfb)
        GL.glBeginTransformFeedback(GL.GL_POINTS)
        self.object.render()
        GL.glEndTransformFeedback()
        GL.glBindTransformFeedback(GL.GL_TRANSFORM_FEEDBACK, 0)
        GL.glDisable(GL.GL_RASTERIZER_DISCARD)

        # Render the two streams.
        colors = [
            np.array([0.8, 0.8, 0.9, 0.5], dtype=np.float32),
            np.array([0.3, 1.0, 0.3, 0.8], dtype=np.float32),
        ]
        GL.glUseProgram(self.render_prog)
        # uniform location 0 = "pass_color" via layout (or first).
        pc_loc: int = GL.glGetUniformLocation(
            program=self.render_prog, name="pass_color"
        )

        GL.glUniform4fv(pc_loc, 1, colors[0])
        GL.glBindVertexArray(self.vao[0])
        GL.glDrawTransformFeedbackStream(GL.GL_TRIANGLES, self.xfb, 0)

        GL.glUniform4fv(pc_loc, 1, colors[1])
        GL.glBindVertexArray(self.vao[1])
        GL.glDrawTransformFeedbackStream(GL.GL_TRIANGLES, self.xfb, 1)

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteProgram(self.sort_prog)
        GL.glDeleteProgram(self.render_prog)
        GL.glDeleteVertexArrays(2, self.vao)
        GL.glDeleteBuffers(2, self.vbo)
        GL.glDeleteTransformFeedbacks(1, [self.xfb])
        self.object.free()


if __name__ == "__main__":
    application.run(cls=DrawXfb, title="DrawTransformFeedback Example")

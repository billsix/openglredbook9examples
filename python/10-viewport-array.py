"""10-viewport-array — geom shader writes to gl_ViewportIndex.

Port of ``src/10-viewport-array/10-viewport-array.cpp``.
``glViewportIndexedf`` sets up four quadrant viewports; the geometry
shader runs with ``invocations = 4`` and routes each invocation's
output to the matching viewport via ``gl_ViewportIndex``. The four
copies of the model use four different model matrices (animated).
"""

from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, vbm, vmath

VS_SOURCE: str = """\
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

GS_SOURCE: str = """\
#version 410

layout (triangles, invocations = 4) in;
layout (triangle_strip, max_vertices = 3) out;

uniform mat4 model_matrix[4];
uniform mat4 projection_matrix;

in vec3 vs_normal[];

out vec4 gs_color;
out vec3 gs_normal;

const vec4 colors[4] = vec4[4]
(
    vec4(1.0, 0.7, 0.3, 1.0),
    vec4(1.0, 0.2, 0.3, 1.0),
    vec4(0.1, 0.6, 1.0, 1.0),
    vec4(0.3, 0.7, 0.5, 1.0)
);

void main(void)
{
    for (int i = 0; i < gl_in.length(); i++)
    {
        gl_ViewportIndex = gl_InvocationID;
        gs_color = colors[gl_InvocationID];
        gs_normal = (model_matrix[gl_InvocationID] * vec4(vs_normal[i], 0.0)).xyz;
        gl_Position = projection_matrix *
                      (model_matrix[gl_InvocationID] * gl_in[i].gl_Position);
        EmitVertex();
    }
}
"""

FS_SOURCE: str = """\
#version 410

layout (location = 0) out vec4 color;

in vec4 gs_color;
in vec3 gs_normal;

void main(void)
{
    color = gs_color * (0.2 + pow(abs(gs_normal.z), 4.0)) + vec4(1.0, 1.0, 1.0, 0.0) * pow(abs(gs_normal.z), 37.0);
}
"""


class ViewportArrayApp(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        self.prog: int = common.compile_program(
            vs=VS_SOURCE, gs=GS_SOURCE, fs=FS_SOURCE
        )
        GL.glUseProgram(self.prog)
        self.model_loc: int = GL.glGetUniformLocation(
            program=self.prog, name="model_matrix"
        )
        self.proj_loc: int = GL.glGetUniformLocation(
            program=self.prog, name="projection_matrix"
        )

        self.object = vbm.VBObject()
        self.object.load(common.media_path("ninja.vbm"))

    @override
    def resize(self, width: int, height: int) -> None:
        # Set up four quadrant viewports.
        wot: float = float(width) * 0.5
        hot: float = float(height) * 0.5
        GL.glViewportIndexedf(0, 0.0, 0.0, wot, hot)
        GL.glViewportIndexedf(1, wot, 0.0, wot, hot)
        GL.glViewportIndexedf(2, 0.0, hot, wot, hot)
        GL.glViewportIndexedf(3, wot, hot, wot, hot)
        self.window_width = width
        self.window_height = height
        self.aspect = hot / max(1.0, wot)

    @override
    def display(self, auto_redraw: bool = True) -> None:
        t: float = float(self.app_time() & 0x3FFF) / float(0x3FFF)

        # imgui's renderer restores GL state with a plain glViewport each
        # frame, which rewrites EVERY viewport in the array to viewport 0's
        # rectangle; the C++ has no imgui and sets the four once in Resize.
        # Re-issue them here so the quadrants survive the frame.
        self.resize(self.window_width, self.window_height)

        GL.glClearColor(0.3, 0.1, 0.2, 1.0)
        GL.glClearDepth(1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int

        GL.glUseProgram(self.prog)

        p: np.ndarray = vmath.frustum(
            left=-1.0,
            right=1.0,
            bottom=self.aspect,
            top=-self.aspect,
            near=1.0,
            far=5000.0,
        )
        mats = []
        two_pi: float = 6.28318531
        import math

        for i in range(4):
            m: np.ndarray = (
                vmath.translate(
                    x=0.0, y=0.0, z=100.0 * math.sin(two_pi * t + i) - 230.0
                )
                @ vmath.rotate(
                    angle_degrees=360.0 * t * (i + 1), ax=1, ay=0, az=0
                )
                @ vmath.rotate(
                    angle_degrees=360.0 * t * (i + 2), ax=0, ay=1, az=0
                )
                @ vmath.rotate(
                    angle_degrees=360.0 * t * (5 - i), ax=0, ay=0, az=1
                )
                @ vmath.translate(x=0.0, y=-80.0, z=0.0)
            )
            mats.append(m)
        vmath.upload_array(location=self.model_loc, mats=mats)
        vmath.upload(location=self.proj_loc, mat=p)

        GL.glEnable(GL.GL_CULL_FACE)
        GL.glCullFace(GL.GL_FRONT)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)

        self.object.render()

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteProgram(self.prog)
        self.object.free()


if __name__ == "__main__":
    application.run(cls=ViewportArrayApp, title="Viewport Array")

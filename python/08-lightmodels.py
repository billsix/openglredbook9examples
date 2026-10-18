"""08-lightmodels — Blinn-Phong lighting on a torus.

Port of ``src/08-lightmodels/08-lightmodels.cpp``. Default
``color_specular`` is ``vec4(0)`` in the shader, so the specular term
is invisible until you uncomment the brighter version. The core
demonstration is ambient + Lambert diffuse with optional specular.
"""

import math
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, vbm, vmath

VS_SOURCE: str = """\
#version 430 core

uniform mat4 model_matrix;
uniform mat4 proj_matrix;

layout (location = 0) in vec4 position;
layout (location = 1) in vec3 normal;

out vec3 vs_worldpos;
out vec3 vs_normal;

void main(void)
{
    vec4 position = proj_matrix * model_matrix * position;
    gl_Position = position;
    vs_worldpos = position.xyz;
    vs_normal = mat3(model_matrix) * normal;
}
"""

FS_SOURCE: str = """\
#version 430 core

layout (location = 0) out vec4 color;

in vec3 vs_worldpos;
in vec3 vs_normal;

uniform vec4 color_ambient = vec4(0.1, 0.2, 0.5, 1.0);
uniform vec4 color_diffuse = vec4(0.2, 0.3, 0.6, 1.0);
uniform vec4 color_specular = vec4(0.0); // vec4(1.0, 1.0, 1.0, 1.0);
uniform float shininess = 77.0f;

uniform vec3 light_position = vec3(12.0f, 32.0f, 560.0f);

void main(void)
{
    vec3 light_direction = normalize(light_position - vs_worldpos);
    vec3 normal = normalize(vs_normal);
    vec3 half_vector = normalize(light_direction + normalize(vs_worldpos));
    float diffuse = max(0.0, dot(normal, light_direction));
    float specular = pow(max(0.0, dot(vs_normal, half_vector)), shininess);
    color = color_ambient + diffuse * color_diffuse + specular * color_specular;
}
"""


class Lighting(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)
        self.render_prog: int = common.compile_program(
            vs=VS_SOURCE, fs=FS_SOURCE
        )
        self.mv_loc: int = GL.glGetUniformLocation(
            program=self.render_prog, name="model_matrix"
        )
        self.prj_loc: int = GL.glGetUniformLocation(
            program=self.render_prog, name="proj_matrix"
        )

        self.object = vbm.VBObject()
        self.object.load(common.media_path("torus.vbm"))

    @override
    def display(self, auto_redraw: bool = True) -> None:
        t: float = float(self.app_time() & 0xFFFF) / float(0xFFFF)

        # Note: 987 * t * pi grows fast — this is in degrees in the
        # C++ vmath::rotate signature. Match it directly.
        mv: np.ndarray = (
            vmath.translate(x=0.0, y=0.0, z=-60.0)
            @ vmath.rotate(angle_degrees=987.0 * t * math.pi, ax=0, ay=0, az=1)
            @ vmath.rotate(angle_degrees=1234.0 * t * math.pi, ax=1, ay=0, az=0)
        )
        prj: np.ndarray = vmath.perspective(
            fovy_degrees=60.0, aspect=1.333, near=0.1, far=1000.0
        )

        GL.glUseProgram(self.render_prog)
        vmath.upload(location=self.mv_loc, mat=mv)
        vmath.upload(location=self.prj_loc, mat=prj)

        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glCullFace(GL.GL_BACK)
        GL.glEnable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)

        self.object.render()

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteProgram(self.render_prog)
        self.object.free()


if __name__ == "__main__":
    application.run(cls=Lighting, title="Lighting Example")

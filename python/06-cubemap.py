"""06-cubemap — cubemap skybox + reflective torus.

Port of ``src/06-cubemap/06-cubemap.cpp``. Uses
``TantolundenCube.dds`` as the environment. Two programs:

  * ``skybox_prog`` draws a unit cube around the camera and samples
    the cubemap with the cube position as the direction vector.
  * ``object_prog`` draws ``torus.vbm``, computes a reflection vector
    in eye space, and looks up the cubemap.

The DDS file is a 6-face cubemap; ``dds.upload_cubemap`` uploads each
face directly via ``glCompressedTexImage2D`` (for DXTn) or
``glTexImage2D`` (for uncompressed).
"""

import ctypes
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, dds, vbm, vmath

SKYBOX_VS: str = """\
#version 330 core

layout (location = 0) in vec3 in_position;

out vec3 tex_coord;

uniform mat4 tc_rotate;

void main(void)
{
    gl_Position = tc_rotate * vec4(in_position, 1.0);
    tex_coord = in_position;
}
"""

SKYBOX_FS: str = """\
#version 330 core

in vec3 tex_coord;

layout (location = 0) out vec4 color;

uniform samplerCube tex;

void main(void)
{
    color = texture(tex, tex_coord);
}
"""

OBJECT_VS: str = """\
#version 330 core

layout (location = 0) in vec4 in_position;
layout (location = 1) in vec3 in_normal;

out vec3 vs_fs_normal;
out vec3 vs_fs_position;

uniform mat4 mat_mvp;
uniform mat4 mat_mv;

void main(void)
{
    gl_Position = mat_mvp * in_position;
    vs_fs_normal = mat3(mat_mv) * in_normal;
    vs_fs_position = (mat_mv * in_position).xyz;
}
"""

OBJECT_FS: str = """\
#version 330 core

in vec3 vs_fs_normal;
in vec3 vs_fs_position;

layout (location = 0) out vec4 color;

uniform samplerCube tex;

void main(void)
{
    vec3 tc =  reflect(vs_fs_position, normalize(vs_fs_normal));
    color = vec4(0.3, 0.2, 0.1, 1.0) + vec4(0.97, 0.83, 0.79, 0.0) * texture(tex, tc);
}
"""


class CubeMapExample(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        self.skybox_prog: int = common.compile_program(
            vs=SKYBOX_VS, fs=SKYBOX_FS
        )
        self.object_prog: int = common.compile_program(
            vs=OBJECT_VS, fs=OBJECT_FS
        )

        self.skybox_rotate_loc: int = GL.glGetUniformLocation(
            program=self.skybox_prog, name="tc_rotate"
        )
        self.object_mvp_loc: int = GL.glGetUniformLocation(
            program=self.object_prog, name="mat_mvp"
        )
        self.object_mv_loc: int = GL.glGetUniformLocation(
            program=self.object_prog, name="mat_mv"
        )

        cube_vertices: np.ndarray = np.array(
            [
                [-1, -1, -1],
                [-1, -1, 1],
                [-1, 1, -1],
                [-1, 1, 1],
                [1, -1, -1],
                [1, -1, 1],
                [1, 1, -1],
                [1, 1, 1],
            ],
            dtype=np.float32,
        )
        cube_indices: np.ndarray = np.array(
            [
                0,
                1,
                2,
                3,
                6,
                7,
                4,
                5,
                2,
                6,
                0,
                4,
                1,
                5,
                3,
                7,
            ],
            dtype=np.uint16,
        )

        self.cube_vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.cube_vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=cube_vertices.nbytes,
            data=cube_vertices,
            usage=GL.GL_STATIC_DRAW,
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

        self.cube_ebo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.cube_ebo)
        GL.glBufferData(
            target=GL.GL_ELEMENT_ARRAY_BUFFER,
            size=cube_indices.nbytes,
            data=cube_indices,
            usage=GL.GL_STATIC_DRAW,
        )

        self.tex: int = dds.upload_cubemap(
            common.media_path("TantolundenCube.dds")
        )

        self.object = vbm.VBObject()
        self.object.load(common.media_path("torus.vbm"))

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
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_TEXTURE_CUBE_MAP_SEAMLESS)

        # Skybox.
        GL.glUseProgram(self.skybox_prog)
        tc: np.ndarray = vmath.perspective(
            fovy_degrees=35.0,
            aspect=1.0 / max(self.aspect, 1e-6),
            near=0.1,
            far=500.0,
        )
        vmath.upload(location=self.skybox_rotate_loc, mat=tc)
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.cube_ebo)
        GL.glDrawElements(
            GL.GL_TRIANGLE_STRIP, 8, GL.GL_UNSIGNED_SHORT, ctypes.c_void_p(0)
        )
        GL.glDrawElements(
            GL.GL_TRIANGLE_STRIP,
            8,
            GL.GL_UNSIGNED_SHORT,
            ctypes.c_void_p(8 * 2),
        )

        # Reflective torus.
        GL.glUseProgram(self.object_prog)
        mv: np.ndarray = (
            vmath.translate(x=0.0, y=0.0, z=-120.0)
            @ vmath.rotate(angle_degrees=80.0 * 3.0 * t, ax=0, ay=1, az=0)
            @ vmath.rotate(angle_degrees=70.0 * 3.0 * t, ax=0, ay=0, az=1)
        )
        mvp = (
            vmath.perspective(
                fovy_degrees=35.0,
                aspect=1.0 / max(self.aspect, 1e-6),
                near=0.1,
                far=500.0,
            )
            @ mv
        )
        vmath.upload(location=self.object_mv_loc, mat=mv)
        vmath.upload(location=self.object_mvp_loc, mat=mvp)

        GL.glClear(GL.GL_DEPTH_BUFFER_BIT)
        self.object.render()

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteProgram(self.skybox_prog)
        GL.glDeleteProgram(self.object_prog)
        GL.glDeleteBuffers(1, [self.cube_vbo])
        GL.glDeleteBuffers(1, [self.cube_ebo])
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteTextures(size=1, array=[self.tex])
        self.object.free()


if __name__ == "__main__":
    application.run(cls=CubeMapExample, title="Cube Map Example")

"""10-fur — geometry-shader fur shells over a base mesh.

Port of ``src/10-fur/10-fur.cpp``. Two passes:

  * ``base_prog`` draws the underlying ninja mesh in solid color.
  * ``fur_prog`` re-emits each input triangle 30 times, each layer
    pushed outward along the vertex normal by ``fur_depth/fur_layers``,
    with alpha sampled from a procedural noisy fur texture and
    fading toward the outermost layer.
"""

from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, vbm, vmath

BASE_VS: str = """\
#version 410

layout (location = 0) in vec4 position_in;
layout (location = 1) in vec3 normal_in;
layout (location = 2) in vec2 texcoord_in;

uniform mat4 model_matrix;
uniform mat4 projection_matrix;

out VS_FS_VERTEX
{
    vec3 normal;
} vertex_out;

void main(void)
{
    vertex_out.normal = normal_in;
    gl_Position = projection_matrix * (model_matrix * position_in);
}
"""

BASE_FS: str = """\
#version 410

layout (location = 0) out vec4 color;

in VS_FS_VERTEX
{
    vec3 normal;
} vertex_in;

void main(void)
{
    vec3 normal = vertex_in.normal;
    color = vec4(0.2, 0.1, 0.5, 1.0) * (0.2 + pow(abs(normal.z), 4.0)) + vec4(0.8, 0.8, 0.8, 0.0) * pow(abs(normal.z), 137.0);
}
"""

FUR_VS: str = """\
#version 410

layout (location = 0) in vec4 position_in;
layout (location = 1) in vec3 normal_in;
layout (location = 2) in vec2 texcoord_in;

out VS_GS_VERTEX
{
    vec3 normal;
    vec2 tex_coord;
} vertex_out;

void main(void)
{
    vertex_out.normal = normal_in;
    vertex_out.tex_coord = texcoord_in;
    gl_Position = position_in;
}
"""

FUR_GS: str = """\
#version 410

layout (triangles) in;
layout (triangle_strip, max_vertices = 240) out;

uniform mat4 model_matrix;
uniform mat4 projection_matrix;

uniform int fur_layers = 30;
uniform float fur_depth = 5.0;

in VS_GS_VERTEX
{
    vec3 normal;
    vec2 tex_coord;
} vertex_in[];

out GS_FS_VERTEX
{
    vec3 normal;
    vec2 tex_coord;
    flat float fur_strength;
} vertex_out;

void main(void)
{
    int i, layer;
    float disp_delta = 1.0 / float(fur_layers);
    float d = 0.0;
    vec4 position;

    for (layer = 0; layer < fur_layers; layer++)
    {
        for (i = 0; i < gl_in.length(); i++) {
            vec3 n = vertex_in[i].normal;
            vertex_out.normal = n;
            vertex_out.tex_coord = vertex_in[i].tex_coord;
            vertex_out.fur_strength = 1.0 - d;
            position = gl_in[i].gl_Position + vec4(n * d * fur_depth, 0.0);
            gl_Position = projection_matrix * (model_matrix * position);
            EmitVertex();
        }
        d += disp_delta;
        EndPrimitive();
    }
}
"""

FUR_FS: str = """\
#version 410

layout (location = 0) out vec4 color;

uniform sampler2D fur_texture;
uniform vec4 fur_color = vec4(0.8, 0.8, 0.9, 1.0);

in GS_FS_VERTEX
{
    vec3 normal;
    vec2 tex_coord;
    flat float fur_strength;
} fragment_in;

void main(void)
{
    vec4 rgba = texture(fur_texture, fragment_in.tex_coord);
    float t = rgba.a;
    t *= fragment_in.fur_strength;
    color = fur_color * vec4(1.0, 1.0, 1.0, t);
}
"""


def _make_fur_texture() -> np.ndarray:
    """Reproduce the C++ ``rand()``-fed fur texture. We don't try to
    match libc's rand exactly — the visual is a stochastic strand
    pattern. Using numpy gives a similar look."""
    rng: np.random.RandomState = np.random.RandomState(0)
    tex: np.ndarray = np.zeros((1024, 1024, 4), dtype=np.uint8)
    for n in range(256):
        # Each layer-strength gets ~1270 random pixels.
        xs: np.ndarray = rng.randint(0, 1024, size=1270)
        ys: np.ndarray = rng.randint(0, 1024, size=1270)
        rgb: np.ndarray = (rng.randint(0, 0x40, size=(1270, 3)) + 0xC0).astype(
            np.uint8
        )
        tex[ys, xs, :3] = rgb
        tex[ys, xs, 3] = n
    return tex


class FurApplication(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        self.base_prog: int = common.compile_program(vs=BASE_VS, fs=BASE_FS)
        self.fur_prog: int = common.compile_program(
            vs=FUR_VS, gs=FUR_GS, fs=FUR_FS
        )

        self.base_model_loc: int = GL.glGetUniformLocation(
            program=self.base_prog, name="model_matrix"
        )
        self.base_proj_loc: int = GL.glGetUniformLocation(
            program=self.base_prog, name="projection_matrix"
        )
        self.fur_model_loc: int = GL.glGetUniformLocation(
            program=self.fur_prog, name="model_matrix"
        )
        self.fur_proj_loc: int = GL.glGetUniformLocation(
            program=self.fur_prog, name="projection_matrix"
        )

        self.fur_texture: int = GL.glGenTextures(1)
        tex_data: np.ndarray = _make_fur_texture()
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.fur_texture)
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D,
            0,
            GL.GL_RGBA,
            1024,
            1024,
            0,
            GL.GL_RGBA,
            GL.GL_UNSIGNED_BYTE,
            tex_data,
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR
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

        GL.glClearColor(0.0, 0.0, 0.0, 1.0)
        GL.glClearDepth(1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int

        # Note: the C++ frustum is called with (top, bottom) reversed:
        # ``frustum(-1, 1, aspect, -aspect, 1, 5000)``. That's not a
        # mistake — it inverts the world Y so the figure stands upright.
        # Reproduce it.
        p: np.ndarray = vmath.frustum(
            left=-1.0,
            right=1.0,
            bottom=self.aspect,
            top=-self.aspect,
            near=1.0,
            far=5000.0,
        )
        m: np.ndarray = (
            vmath.translate(x=0.0, y=0.0, z=-130.0)
            @ vmath.rotate(angle_degrees=360.0 * t, ax=0, ay=1, az=0)
            @ vmath.rotate(angle_degrees=180.0, ax=0, ay=0, az=1)
            @ vmath.translate(x=0.0, y=-80.0, z=0.0)
        )

        GL.glUseProgram(self.base_prog)
        vmath.upload(location=self.base_model_loc, mat=m)
        vmath.upload(location=self.base_proj_loc, mat=p)
        GL.glDisable(GL.GL_BLEND)
        GL.glEnable(GL.GL_CULL_FACE)
        GL.glCullFace(GL.GL_FRONT)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        self.object.render()

        GL.glUseProgram(self.fur_prog)
        vmath.upload(location=self.fur_model_loc, mat=m)
        vmath.upload(location=self.fur_proj_loc, mat=p)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.fur_texture)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDepthMask(GL.GL_FALSE)
        self.object.render()
        GL.glDepthMask(GL.GL_TRUE)
        GL.glDisable(GL.GL_BLEND)

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteProgram(self.base_prog)
        GL.glDeleteProgram(self.fur_prog)
        GL.glDeleteTextures(size=1, array=[self.fur_texture])
        self.object.free()


if __name__ == "__main__":
    application.run(cls=FurApplication, title="Fur Rendering")

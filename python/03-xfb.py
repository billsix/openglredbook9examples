"""03-xfb — transform feedback particles bouncing off a mesh.

Port of ``src/03-xfb/03-xfb.cpp``.

Two programs:
  * ``render_prog`` draws the armadillo mesh; its TF varying captures
    the world-space position of each emitted vertex into ``geometry_vbo``,
    which is also bound as a ``samplerBuffer`` for the update pass to
    look up triangle vertices.
  * ``update_prog`` runs once per particle, doing ray-triangle
    intersection against the captured geometry to bounce velocities;
    its TF varyings feed back into the next frame's particle VBO.

The double-buffered XFB pattern uses two VAO/VBO pairs and alternates
which is read vs written each frame.
"""

import ctypes
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, vbm, vmath

POINT_COUNT: int = 5000


UPDATE_VS: str = """\
#version 410

uniform mat4 model_matrix;
uniform mat4 projection_matrix;
uniform int triangle_count;

layout (location = 0) in vec4 position;
layout (location = 1) in vec3 velocity;

out vec4 position_out;
out vec3 velocity_out;

uniform samplerBuffer geometry_tbo;
uniform float time_step = 0.02;

bool intersect(vec3 origin, vec3 direction, vec3 v0, vec3 v1, vec3 v2, out vec3 point)
{
    vec3 u, v, n;
    vec3 w0, w;
    float r, a, b;

    u = (v1 - v0);
    v = (v2 - v0);
    n = cross(u, v);
    if (length(n) < 0.1)
        return false;

    w0 = origin - v0;
    a = -dot(n, w0);
    b = dot(n, direction);
    if (abs(b) < 0.1)
        return false;

    r = a / b;
    if (r < 0.0 || r > 1.0)
        return false;

    point = origin + r * direction;

    float uu, uv, vv, wu, wv, D;

    uu = dot(u, u);
    uv = dot(u, v);
    vv = dot(v, v);
    w = point - v0;
    wu = dot(w, u);
    wv = dot(w, v);
    D = uv * uv - uu * vv;

    float s, t;

    s = (uv * wv - vv * wu) / D;
    if (s < 0.0 || s > 1.0)
        return false;
    t = (uv * wu - uu * wv) / D;
    if (t < 0.0 || (s + t) > 1.0)
        return false;

    return true;
}

vec3 reflect_vector(vec3 v, vec3 n)
{
    return v - 2.0 * dot(v, n) * n;
}

void main(void)
{
    vec3 accelleration = vec3(0.0, -0.3, 0.0);
    vec3 new_velocity = velocity + accelleration * time_step;
    vec4 new_position = position + vec4(new_velocity * time_step, 0.0);
    vec3 v0, v1, v2;
    vec3 point;
    int i;
    for (i = 0; i < triangle_count; i++)
    {
        v0 = texelFetch(geometry_tbo, i * 3).xyz;
        v1 = texelFetch(geometry_tbo, i * 3 + 1).xyz;
        v2 = texelFetch(geometry_tbo, i * 3 + 2).xyz;
        if (intersect(position.xyz, position.xyz - new_position.xyz, v0, v1, v2, point))
        {
            vec3 n = normalize(cross(v1 - v0, v2 - v0));
            new_position = vec4(point + reflect_vector(new_position.xyz - point, n), 1.0);
            new_velocity = 0.8 * reflect_vector(new_velocity, n);
        }
    }
    if (new_position.y < -40.0)
    {
        new_position = vec4(-new_position.x * 0.3, position.y + 80.0, 0.0, 1.0);
        new_velocity *= vec3(0.2, 0.1, -0.3);
    }
    velocity_out = new_velocity * 0.9999;
    position_out = new_position;
    gl_Position = projection_matrix * (model_matrix * position);
}
"""

WHITE_FS: str = """\
#version 410

layout (location = 0) out vec4 color;

void main(void)
{
    color = vec4(1.0);
}
"""

RENDER_VS: str = """\
#version 410

uniform mat4 model_matrix;
uniform mat4 projection_matrix;

layout (location = 0) in vec4 position;
layout (location = 1) in vec3 normal;

out vec4 world_space_position;

out vec3 vs_fs_normal;

void main(void)
{
    vec4 pos = (model_matrix * (position * vec4(1.0, 1.0, 1.0, 1.0)));
    world_space_position = pos;
    vs_fs_normal = normalize((model_matrix * vec4(normal, 0.0)).xyz);
    gl_Position = projection_matrix * pos;
}
"""

BLUE_FS: str = """\
#version 410

layout (location = 0) out vec4 color;

in vec3 vs_fs_normal;

void main(void)
{
    color = vec4(0.0, 0.2, 0.0, 1.0) + vec4(0.2, 0.5, 0.4, 1.0) * abs(vs_fs_normal.z) + vec4(0.8, 0.9, 0.7, 1.0) * pow(abs(vs_fs_normal.z), 70.0);
}
"""


class TransformFeedbackExample(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        self._frame = 0
        self._q = 0.0

        # Update program (capture position_out / velocity_out).
        self.update_prog: int = common.compile_program(
            vs=UPDATE_VS,
            fs=WHITE_FS,
            tf_varyings=["position_out", "velocity_out"],
            tf_buffer_mode=GL.GL_INTERLEAVED_ATTRIBS,
        )
        GL.glUseProgram(self.update_prog)
        self.u_model: int = GL.glGetUniformLocation(
            program=self.update_prog, name="model_matrix"
        )
        self.u_proj: int = GL.glGetUniformLocation(
            program=self.update_prog, name="projection_matrix"
        )
        self.u_tri_count: int = GL.glGetUniformLocation(
            program=self.update_prog, name="triangle_count"
        )
        self.u_time_step: int = GL.glGetUniformLocation(
            program=self.update_prog, name="time_step"
        )

        # Render program (capture world_space_position).
        self.render_prog: int = common.compile_program(
            vs=RENDER_VS,
            fs=BLUE_FS,
            tf_varyings=["world_space_position"],
            tf_buffer_mode=GL.GL_INTERLEAVED_ATTRIBS,
        )
        GL.glUseProgram(self.render_prog)
        self.r_model: int = GL.glGetUniformLocation(
            program=self.render_prog, name="model_matrix"
        )
        self.r_proj: int = GL.glGetUniformLocation(
            program=self.render_prog, name="projection_matrix"
        )

        # Two ping-pong VAO/VBO pairs holding (vec4 position, vec3 velocity)
        # interleaved — stride = 28 bytes.
        self.vao = GL.glGenVertexArrays(2)
        self.vbo = GL.glGenBuffers(2)
        stride: int = 28
        for i in range(2):
            GL.glBindBuffer(GL.GL_TRANSFORM_FEEDBACK_BUFFER, self.vbo[i])
            GL.glBufferData(
                target=GL.GL_TRANSFORM_FEEDBACK_BUFFER,
                size=POINT_COUNT * stride,
                data=None,
                usage=GL.GL_DYNAMIC_COPY,
            )

        # Seed buffer 0 with random points.
        seed = np.random.RandomState(0x13371337)
        random_dirs = (
            seed.random_sample((POINT_COUNT, 3)).astype(np.float32) * 2.0 - 1.0
        )
        random_dirs /= np.linalg.norm(random_dirs, axis=1, keepdims=True)
        magnitudes = seed.random_sample((POINT_COUNT, 1)).astype(np.float32)
        random_dirs *= magnitudes
        # buffer entry: vec4 position, vec3 velocity
        positions: np.ndarray = np.zeros((POINT_COUNT, 4), dtype=np.float32)
        positions[:, :3] = random_dirs + np.array(
            [-0.5, 40.0, 0.0], dtype=np.float32
        )
        positions[:, 3] = 1.0
        velocities = random_dirs.copy()
        velocities[:, 1] *= 0.3
        velocities[:, 2] *= 0.3
        # Pack into a single byte buffer of stride 28.
        seeded: np.ndarray = np.empty((POINT_COUNT, 7), dtype=np.float32)
        seeded[:, :4] = positions
        seeded[:, 4:] = velocities
        GL.glBindBuffer(GL.GL_TRANSFORM_FEEDBACK_BUFFER, self.vbo[0])
        GL.glBufferSubData(
            target=GL.GL_TRANSFORM_FEEDBACK_BUFFER,
            offset=0,
            size=seeded.nbytes,
            data=seeded,
        )

        for i in range(2):
            GL.glBindVertexArray(self.vao[i])
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo[i])
            GL.glVertexAttribPointer(
                index=0,
                size=4,
                type=GL.GL_FLOAT,
                normalized=GL.GL_FALSE,
                stride=stride,
                pointer=ctypes.c_void_p(0),
            )
            GL.glVertexAttribPointer(
                index=1,
                size=3,
                type=GL.GL_FLOAT,
                normalized=GL.GL_FALSE,
                stride=stride,
                pointer=ctypes.c_void_p(16),
            )
            GL.glEnableVertexAttribArray(0)
            GL.glEnableVertexAttribArray(1)

        # Geometry buffer + samplerBuffer texture.
        self.geometry_vbo: int = GL.glGenBuffers(1)
        self.geometry_tex: int = GL.glGenTextures(1)
        GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, self.geometry_vbo)
        GL.glBufferData(
            target=GL.GL_TEXTURE_BUFFER,
            size=1024 * 1024 * 16,
            data=None,
            usage=GL.GL_DYNAMIC_COPY,
        )
        GL.glBindTexture(GL.GL_TEXTURE_BUFFER, self.geometry_tex)
        GL.glTexBuffer(GL.GL_TEXTURE_BUFFER, GL.GL_RGBA32F, self.geometry_vbo)

        # Render-VAO: a single position attribute pulled from
        # geometry_vbo, used to redraw the captured geometry as a
        # point cloud (the C++ uses it but the actual rendering of the
        # mesh happens via the VBM object).
        self.render_vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.render_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.geometry_vbo)
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
        GL.glClearDepth(1.0)

        # Mesh used as both renderable geometry and TF source.
        self.object = vbm.VBObject()
        self.object.load(common.media_path("armadillo_low.vbm"))

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.aspect = float(height) / float(max(1, width))

    @override
    def display(self, auto_redraw: bool = True) -> None:
        t: float = float(self.app_time() & 0x3FFFF) / float(0x3FFFF)

        proj: np.ndarray = vmath.frustum(
            left=-1.0,
            right=1.0,
            bottom=-self.aspect,
            top=self.aspect,
            near=1.0,
            far=5000.0,
        ) @ vmath.translate(x=0.0, y=0.0, z=-100.0)
        model: np.ndarray = (
            vmath.scale(0.3)
            @ vmath.rotate(angle_degrees=t * 360.0, ax=0, ay=1, az=0)
            @ vmath.rotate(angle_degrees=t * 360.0 * 3.0, ax=0, ay=0, az=1)
        )

        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glEnable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)

        # Pass 1: render mesh and capture world-space positions to
        # geometry_vbo.
        GL.glUseProgram(self.render_prog)
        vmath.upload(location=self.r_model, mat=model)
        vmath.upload(location=self.r_proj, mat=proj)

        GL.glBindVertexArray(self.render_vao)
        GL.glBindBufferBase(
            GL.GL_TRANSFORM_FEEDBACK_BUFFER, 0, self.geometry_vbo
        )
        GL.glBeginTransformFeedback(GL.GL_TRIANGLES)
        self.object.render()
        GL.glEndTransformFeedback()

        # Pass 2: update particles. Read previous-frame buffer, write
        # next-frame buffer.
        GL.glUseProgram(self.update_prog)
        identity: np.ndarray = vmath.identity()
        vmath.upload(location=self.u_model, mat=identity)
        vmath.upload(location=self.u_proj, mat=proj)
        GL.glUniform1i(self.u_tri_count, self.object.num_vertices // 3)

        if t > self._q:
            GL.glUniform1f(self.u_time_step, (t - self._q) * 2000.0)
        self._q = t

        if (self._frame & 1) != 0:
            GL.glBindVertexArray(self.vao[1])
            GL.glBindBufferBase(GL.GL_TRANSFORM_FEEDBACK_BUFFER, 0, self.vbo[0])
        else:
            GL.glBindVertexArray(self.vao[0])
            GL.glBindBufferBase(GL.GL_TRANSFORM_FEEDBACK_BUFFER, 0, self.vbo[1])

        GL.glBeginTransformFeedback(GL.GL_POINTS)
        GL.glDrawArrays(GL.GL_POINTS, 0, min(POINT_COUNT, self._frame >> 3))
        GL.glEndTransformFeedback()

        GL.glBindVertexArray(0)
        self._frame += 1

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteProgram(self.update_prog)
        GL.glDeleteProgram(self.render_prog)
        GL.glDeleteVertexArrays(2, self.vao)
        GL.glDeleteBuffers(2, self.vbo)
        GL.glDeleteBuffers(1, [self.geometry_vbo])
        GL.glDeleteTextures(size=1, array=[self.geometry_tex])
        GL.glDeleteVertexArrays(1, [self.render_vao])
        self.object.free()


if __name__ == "__main__":
    application.run(
        cls=TransformFeedbackExample, title="TransformFeedback Example"
    )

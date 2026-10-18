"""12-particlesimulator — 8M particles updated by a compute shader.

Port of ``src/12-particlesimulator/12-particlesimulator.cpp``.

Two TBOs (position, velocity) plus a UBO of 64 ``vec4`` attractors.
Each compute work-group of 1024 invocations updates 1024 particles by
summing gravitational pulls from the first 4 attractors. The
attractors animate in a sin/cos pattern. Render pass: VAO over the
position buffer, draws ``GL_POINTS`` with additive blend.

The particle count is the C++ default, 1024 × 8192 = 8,388,608 (128 MiB
for the two buffers); ``REDBOOK9_PARTICLE_GROUPS`` overrides the group
count (``1024`` → 1 M particles) when that is too much for the machine.
The seed uses numpy's generator rather than the C++ xorshift, with the
same ball-shaped distribution.
"""

import ctypes
import math
import os
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, vmath

PARTICLE_GROUP_SIZE: int = 1024
DEFAULT_GROUP_COUNT: int = 8192
MAX_ATTRACTORS: int = 64


def _random_vectors(
    rng: np.random.RandomState, n: int, minmag: float, maxmag: float
) -> np.ndarray:
    """The C++ ``random_vector(minmag, maxmag)``, ``n`` rows at a time: a
    unit direction times a magnitude uniform in ``[minmag, maxmag]``."""
    direction: np.ndarray = rng.random_sample((n, 3)) * 2 - 1
    direction /= np.linalg.norm(direction, axis=1, keepdims=True)
    magnitude: np.ndarray = (
        rng.random_sample((n, 1)) * (maxmag - minmag) + minmag
    )
    return (direction * magnitude).astype(np.float32)


def _particle_count() -> int:
    env = os.environ.get("REDBOOK9_PARTICLE_GROUPS")
    return PARTICLE_GROUP_SIZE * int(env if env else DEFAULT_GROUP_COUNT)


COMPUTE_SOURCE: str = """\
#version 430 core


layout (std140, binding = 0) uniform attractor_block
{
    vec4 attractor[64]; // xyz = position, w = mass
};

layout (local_size_x = 1024) in;

layout (rgba32f, binding = 0) uniform imageBuffer velocity_buffer;
layout (rgba32f, binding = 1) uniform imageBuffer position_buffer;

uniform float dt = 1.0;

void main(void)
{
    vec4 vel = imageLoad(velocity_buffer, int(gl_GlobalInvocationID.x));
    vec4 pos = imageLoad(position_buffer, int(gl_GlobalInvocationID.x));

    int i;

    pos.xyz += vel.xyz * dt;
    pos.w -= 0.0001 * dt;

    for (i = 0; i < 4; i++)
    {
        vec3 dist = (attractor[i].xyz - pos.xyz);
        vel.xyz += dt * dt * attractor[i].w * normalize(dist) / (dot(dist, dist) + 10.0);
    }

    if (pos.w <= 0.0)
    {
        pos.xyz = -pos.xyz * 0.01;
        vel.xyz *= 0.01;
        pos.w += 1.0f;
    }

    imageStore(position_buffer, int(gl_GlobalInvocationID.x), pos);
    imageStore(velocity_buffer, int(gl_GlobalInvocationID.x), vel);
}
        """

RENDER_VS: str = """\
#version 430 core

in vec4 vert;

uniform mat4 mvp;

out float intensity;

void main(void)
{
    intensity = vert.w;
    gl_Position = mvp * vec4(vert.xyz, 1.0);
}
"""

RENDER_FS: str = """\
#version 430 core

layout (location = 0) out vec4 color;

in float intensity;

void main(void)
{
    color = mix(vec4(0.0f, 0.2f, 1.0f, 1.0f), vec4(0.2f, 0.05f, 0.0f, 1.0f), intensity);
}
"""


class ComputeParticleSimulator(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect_ratio = 1.0
        self.particle_count = _particle_count()
        self.particle_groups = self.particle_count // PARTICLE_GROUP_SIZE
        self._last_ticks = self.app_time()
        self._start_ticks = self.app_time() - 100000

        self.compute_prog: int = common.compile_program(cs=COMPUTE_SOURCE)
        self.dt_loc: int = GL.glGetUniformLocation(
            program=self.compute_prog, name="dt"
        )

        self.render_vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.render_vao)

        rng = np.random.RandomState(0xFFFF0C59)

        # Position buffer.
        self.position_buffer: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.position_buffer)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=self.particle_count * 16,
            data=None,
            usage=GL.GL_DYNAMIC_COPY,
        )
        positions: np.ndarray = np.zeros(
            (self.particle_count, 4), dtype=np.float32
        )
        # random_vector(-10, 10): a unit direction scaled by a signed
        # magnitude uniform in [-10, 10] -- a radially uniform ball, dense
        # at the centre, not a cube. (numpy's generator replaces the C++
        # xorshift; the distribution is the same, the sequence is not.)
        positions[:, :3] = _random_vectors(
            rng=rng, n=self.particle_count, minmag=-10.0, maxmag=10.0
        )
        positions[:, 3] = rng.random_sample(self.particle_count)
        GL.glBufferSubData(
            target=GL.GL_ARRAY_BUFFER,
            offset=0,
            size=positions.nbytes,
            data=positions,
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

        # Velocity buffer.
        self.velocity_buffer: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.velocity_buffer)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=self.particle_count * 16,
            data=None,
            usage=GL.GL_DYNAMIC_COPY,
        )
        velocities: np.ndarray = np.zeros(
            (self.particle_count, 4), dtype=np.float32
        )
        # random_vector(-0.1, 0.1), as for the positions.
        velocities[:, :3] = _random_vectors(
            rng=rng, n=self.particle_count, minmag=-0.1, maxmag=0.1
        )
        GL.glBufferSubData(
            target=GL.GL_ARRAY_BUFFER,
            offset=0,
            size=velocities.nbytes,
            data=velocities,
        )

        # TBOs over the two buffers.
        self.position_tbo: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_BUFFER, self.position_tbo)
        GL.glTexBuffer(
            GL.GL_TEXTURE_BUFFER, GL.GL_RGBA32F, self.position_buffer
        )
        self.velocity_tbo: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_BUFFER, self.velocity_tbo)
        GL.glTexBuffer(
            GL.GL_TEXTURE_BUFFER, GL.GL_RGBA32F, self.velocity_buffer
        )

        # Attractor UBO (64 vec4).
        self.attractor_buffer: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_UNIFORM_BUFFER, self.attractor_buffer)
        GL.glBufferData(
            target=GL.GL_UNIFORM_BUFFER,
            size=MAX_ATTRACTORS * 16,
            data=None,
            usage=GL.GL_STATIC_DRAW,
        )
        GL.glBindBufferBase(GL.GL_UNIFORM_BUFFER, 0, self.attractor_buffer)

        self.attractor_masses = (
            0.5 + rng.random_sample(MAX_ATTRACTORS) * 0.5
        ).astype(np.float32)

        self.render_prog: int = common.compile_program(
            vs=RENDER_VS, fs=RENDER_FS
        )

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.aspect_ratio = float(width) / float(max(1, height))

    @override
    def display(self, auto_redraw: bool = True) -> None:
        current_ticks = self.app_time()
        # Note: C++ has the subtraction inverted (start - current),
        # which produces a slowly-increasing-and-wrapping value because
        # of the `& 0xFFFFF` mask. Match it.
        time = ((self._start_ticks - current_ticks) & 0xFFFFF) / 0xFFFFF
        delta_time = (current_ticks - self._last_ticks) * 0.075
        if delta_time < 0.01:
            return

        # Animate the 32 active attractors.
        attractors: np.ndarray = np.zeros((MAX_ATTRACTORS, 4), dtype=np.float32)
        for i in range(32):
            attractors[i, 0] = math.sin(time * (i + 4) * 7.5 * 20.0) * 50.0
            attractors[i, 1] = math.cos(time * (i + 7) * 3.9 * 20.0) * 50.0
            attractors[i, 2] = (
                math.sin(time * (i + 3) * 5.3 * 20.0)
                * math.cos(time * (i + 5) * 9.1)
                * 100.0
            )
            attractors[i, 3] = self.attractor_masses[i]
        GL.glBindBuffer(GL.GL_UNIFORM_BUFFER, self.attractor_buffer)
        GL.glBufferSubData(
            target=GL.GL_UNIFORM_BUFFER,
            offset=0,
            size=attractors.nbytes,
            data=attractors,
        )

        delta_time = min(2.0, delta_time)

        GL.glUseProgram(self.compute_prog)
        GL.glBindImageTexture(
            0,
            self.velocity_tbo,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_READ_WRITE,
            GL.GL_RGBA32F,
        )
        GL.glBindImageTexture(
            1,
            self.position_tbo,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_READ_WRITE,
            GL.GL_RGBA32F,
        )
        GL.glUniform1f(self.dt_loc, delta_time)
        GL.glDispatchCompute(self.particle_groups, 1, 1)
        # The compute pass wrote position_buffer through an image; the draw
        # below reads it as attribute 0, so Mesa needs the vertex-attrib
        # barrier too (mesa-and-pyopengl-traps.md §2).
        GL.glMemoryBarrier(
            GL.GL_SHADER_IMAGE_ACCESS_BARRIER_BIT
            | GL.GL_VERTEX_ATTRIB_ARRAY_BARRIER_BIT  # ty: ignore[unsupported-operator]
        )

        mvp: np.ndarray = (
            vmath.perspective(
                fovy_degrees=45.0,
                aspect=self.aspect_ratio,
                near=0.1,
                far=1000.0,
            )
            @ vmath.translate(x=0.0, y=0.0, z=-160.0)
            @ vmath.rotate(angle_degrees=time * 1000.0, ax=0, ay=1, az=0)
        )
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(self.render_prog)
        # Uniform location 0 = "mvp" (first uniform).
        mvp_loc: int = GL.glGetUniformLocation(
            program=self.render_prog, name="mvp"
        )
        vmath.upload(location=mvp_loc, mat=mvp)
        GL.glBindVertexArray(self.render_vao)
        # Re-bind the position buffer as the array attribute for this VAO.
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.position_buffer)
        GL.glVertexAttribPointer(
            index=0,
            size=4,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )
        GL.glEnableVertexAttribArray(0)

        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE)
        GL.glDrawArrays(GL.GL_POINTS, 0, self.particle_count)
        GL.glDisable(GL.GL_BLEND)

        self._last_ticks = current_ticks
        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteProgram(self.compute_prog)
        GL.glDeleteProgram(self.render_prog)
        GL.glDeleteVertexArrays(1, [self.render_vao])
        GL.glDeleteBuffers(1, [self.position_buffer])
        GL.glDeleteBuffers(1, [self.velocity_buffer])
        GL.glDeleteBuffers(1, [self.attractor_buffer])
        GL.glDeleteTextures(size=1, array=[self.position_tbo])
        GL.glDeleteTextures(size=1, array=[self.velocity_tbo])


if __name__ == "__main__":
    application.run(
        cls=ComputeParticleSimulator, title="Compute Shader Particle System"
    )

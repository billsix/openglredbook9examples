"""12-raytracer — minimal compute-shader ray tracer skeleton.

Port of ``src/12-raytracer/12-raytracer.cpp``. The C++ side
is itself a skeleton: it sets up two SSBOs of RAY records plus an
atomic-counter-pair buffer (consume + append), runs an
``initializer_prog`` to seed rays for each pixel, then runs a
``trace_prog`` that consumes rays from the input buffer, writes one
sample to the image, and pushes two perturbed rays into the output
buffer for the next bounce. This port preserves that skeleton 1:1; in
particular it does not add a sphere/scene-intersect step (the C++
doesn't either).
"""

import ctypes
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common

OUTPUT_LODS: int = 9
OUTPUT_SIZE_X = 1 << OUTPUT_LODS
OUTPUT_SIZE_Y = 1 << OUTPUT_LODS


RAY_ELEMENT: str = """\
struct RAY
{
    ivec4 screen_origin;
    vec4  world_origin;
    vec4  world_direction;
};
"""

INIT_SOURCE = (
    """\
#version 430 core

layout (local_size_x = 16, local_size_y = 16) in;

"""
    + RAY_ELEMENT
    + """

layout (std430, binding = 0) buffer ray_buffer
{
    RAY ray[];
};

RAY initialize_ray()
{
    RAY r;
    r.screen_origin.xy = ivec2(gl_GlobalInvocationID.xy);
    r.world_origin.xyz = vec3(0.0, 0.0, 0.0);
    // Upstream uses ``vec2(gl_LocalInvocationID.xy)`` (range 0..15)
    // for x/y, which makes every 16x16 tile produce the same
    // direction gradient and the output looks like a grid of blue
    // squares. We use the global pixel coords mapped to NDC [-1, +1]
    // so the entire image becomes a smooth direction-colored ramp.
    vec2 ndc = vec2(gl_GlobalInvocationID.xy) /
               vec2(gl_NumWorkGroups.xy * gl_WorkGroupSize.xy) * 2.0 - 1.0;
    r.world_direction.xyz = normalize(vec3(ndc, 1.0));
    return r;
}

void main(void)
{
    // The C++ source writes to ``ray[gl_LocalInvocationID.y * 16 +
    // gl_LocalInvocationID.x]`` — this is a bug in the upstream demo:
    // the dispatch is 32×32 work groups, so all 1024 work groups race
    // to the same 256 buffer slots and only ~256 valid rays end up in
    // the buffer. The trace pass then consumes 262144 rays via an
    // atomic counter, reading ~262000 uninitialized slots and
    // producing visual noise. We use ``gl_GlobalInvocationID`` so the
    // buffer ends up with one valid ray per output pixel (512×512 =
    // 262144 rays = the dispatch's invocation count).
    uvec3 wgs = gl_NumWorkGroups * gl_WorkGroupSize;
    uint idx = gl_GlobalInvocationID.y * wgs.x + gl_GlobalInvocationID.x;
    ray[idx] = initialize_ray();
}
"""
)

TRACE_SOURCE = """\
#version 430 core

layout (local_size_x = 16, local_size_y = 16) in;

struct RAY
{
    ivec4  screen_origin;
    vec4   world_origin;
    vec4   world_direction;
};

layout (std430, binding = 0) buffer input_ray_buffer
{
    RAY    ray[];
} input_buffer;

layout (std430, binding = 1) buffer output_ray_buffer
{
    RAY    ray[];
} output_buffer;

layout (binding = 0, offset = 0) uniform atomic_uint consume_counter;
layout (binding = 0, offset = 4) uniform atomic_uint append_counter;

layout (rgba32f, binding = 0) uniform image2D output_image;

void main(void)
{
    uint ray_index = atomicCounterIncrement(consume_counter);

    RAY input_ray = input_buffer.ray[ray_index];

    barrier();

    {
        imageStore(output_image, input_ray.screen_origin.xy, vec4(input_ray.world_direction.xyz, 1.0));
        ray_index = atomicCounterIncrement(append_counter);
        input_ray.world_direction.x += 0.01;
        output_buffer.ray[ray_index] = input_ray;
        ray_index = atomicCounterIncrement(append_counter);
        input_ray.world_direction.y += 0.01;
        output_buffer.ray[ray_index] = input_ray;
    }
}
"""

RENDER_VS: str = """\
#version 430 core

in vec4 vert;

void main(void)
{
    gl_Position = vert;
}
"""

RENDER_FS: str = """\
#version 430 core

layout (location = 0) out vec4 color;

uniform sampler2D output_image;

void main(void)
{
    color = texture(output_image, vec2(gl_FragCoord.xy) / vec2(textureSize(output_image, 0)));
}
"""


class RayTracer(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.ray_buffer = GL.glGenBuffers(2)
        for b in self.ray_buffer:
            GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER, b)
            GL.glBufferData(
                target=GL.GL_SHADER_STORAGE_BUFFER,
                size=64 * 1024 * 1024,
                data=None,
                usage=GL.GL_DYNAMIC_COPY,
            )

        zeros: np.ndarray = np.zeros(2, dtype=np.uint32)
        self.counter_buffer: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ATOMIC_COUNTER_BUFFER, self.counter_buffer)
        GL.glBufferData(
            target=GL.GL_ATOMIC_COUNTER_BUFFER,
            size=zeros.nbytes,
            data=zeros,
            usage=GL.GL_DYNAMIC_COPY,
        )

        self.initializer_prog: int = common.compile_program(cs=INIT_SOURCE)
        self.trace_prog: int = common.compile_program(cs=TRACE_SOURCE)

        self.output_image: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.output_image)
        GL.glTexStorage2D(
            GL.GL_TEXTURE_2D,
            OUTPUT_LODS,
            GL.GL_RGBA32F,
            OUTPUT_SIZE_X,
            OUTPUT_SIZE_Y,
        )

        self.render_prog: int = common.compile_program(
            vs=RENDER_VS, fs=RENDER_FS
        )

        self.render_vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.render_vao)
        GL.glEnableVertexAttribArray(0)
        self.render_vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.render_vbo)
        verts: np.ndarray = np.array(
            [
                [-1.0, -1.0, 0.5, 1.0],
                [1.0, -1.0, 0.5, 1.0],
                [1.0, 1.0, 0.5, 1.0],
                [-1.0, 1.0, 0.5, 1.0],
            ],
            dtype=np.float32,
        )
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=verts.nbytes,
            data=verts,
            usage=GL.GL_STATIC_DRAW,
        )
        GL.glVertexAttribPointer(
            index=0,
            size=4,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )

    @override
    def display(self, auto_redraw: bool = True) -> None:
        # initialize-pass.
        GL.glUseProgram(self.initializer_prog)
        GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER, 0, self.ray_buffer[0])
        GL.glDispatchCompute(OUTPUT_SIZE_X // 16, OUTPUT_SIZE_Y // 16, 1)

        # Reset atomic counters to 0,0.
        zeros = np.zeros(2, dtype=np.uint32)
        GL.glBindBufferBase(GL.GL_ATOMIC_COUNTER_BUFFER, 0, self.counter_buffer)
        GL.glBufferData(
            target=GL.GL_ATOMIC_COUNTER_BUFFER,
            size=zeros.nbytes,
            data=zeros,
            usage=GL.GL_DYNAMIC_COPY,
        )

        GL.glBindImageTexture(
            0,
            self.output_image,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_READ_WRITE,
            GL.GL_RGBA32F,
        )

        GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER, 0, self.ray_buffer[0])
        GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER, 1, self.ray_buffer[1])

        # Mesa needs the barrier so trace_prog sees the rays the
        # initializer just wrote (SSBO) and the just-zeroed atomic
        # counters. Same lesson as the chap-11 demos.
        GL.glMemoryBarrier(
            GL.GL_SHADER_STORAGE_BARRIER_BIT | GL.GL_ATOMIC_COUNTER_BARRIER_BIT  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        )

        GL.glUseProgram(self.trace_prog)
        GL.glDispatchCompute(OUTPUT_SIZE_X // 16, OUTPUT_SIZE_Y // 16, 1)

        # And before the render pass samples output_image as a texture,
        # ensure trace_prog's imageStore writes have landed.
        GL.glMemoryBarrier(GL.GL_TEXTURE_FETCH_BARRIER_BIT)

        GL.glBindTexture(GL.GL_TEXTURE_2D, self.output_image)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glUseProgram(self.render_prog)
        GL.glDrawArrays(GL.GL_TRIANGLE_FAN, 0, 4)

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteProgram(self.initializer_prog)
        GL.glDeleteProgram(self.trace_prog)
        GL.glDeleteProgram(self.render_prog)
        GL.glDeleteBuffers(2, self.ray_buffer)
        GL.glDeleteBuffers(1, [self.counter_buffer])
        GL.glDeleteBuffers(1, [self.render_vbo])
        GL.glDeleteVertexArrays(1, [self.render_vao])
        GL.glDeleteTextures(size=1, array=[self.output_image])


if __name__ == "__main__":
    application.run(cls=RayTracer, title="Compute Shader Raytracing Example")

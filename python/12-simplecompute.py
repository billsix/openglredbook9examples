"""12-simplecompute — minimal compute shader writes a gradient.

Port of ``src/12-simplecompute/12-simplecompute.cpp``.

The compute shader fills a 256×256 texture with a horizontal gradient
based on local invocation IDs. Then a tiny VS/FS pair samples that
texture and draws a fullscreen quad. Smallest possible
"compute → texture → draw" pipeline in v9.
"""

import ctypes
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common

COMPUTE_SOURCE: str = """\
#version 430 core

layout (local_size_x = 32, local_size_y = 16) in;

layout (rgba32f) uniform image2D output_image;
void main(void)
{
    imageStore(output_image,
    ivec2(gl_GlobalInvocationID.xy),
    vec4(vec2(gl_LocalInvocationID.xy) / vec2(gl_WorkGroupSize.xy), 0.0, 0.0));
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


class SimpleCompute(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.compute_prog: int = common.compile_program(cs=COMPUTE_SOURCE)

        self.output_image: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.output_image)
        GL.glTexStorage2D(GL.GL_TEXTURE_2D, 8, GL.GL_RGBA32F, 256, 256)

        self.render_prog: int = common.compile_program(
            vs=RENDER_VS, fs=RENDER_FS
        )

        self.vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        GL.glEnableVertexAttribArray(0)
        self.vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
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
        GL.glUseProgram(self.compute_prog)
        GL.glBindImageTexture(
            0,
            self.output_image,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_WRITE_ONLY,
            GL.GL_RGBA32F,
        )
        GL.glDispatchCompute(8, 16, 1)
        # imageStore -> texture(): Mesa needs the fetch barrier
        # (mesa-and-pyopengl-traps.md §2); the C++ has none.
        GL.glMemoryBarrier(GL.GL_TEXTURE_FETCH_BARRIER_BIT)

        GL.glBindTexture(GL.GL_TEXTURE_2D, self.output_image)

        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        GL.glUseProgram(self.render_prog)
        GL.glDrawArrays(GL.GL_TRIANGLE_FAN, 0, 4)

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteProgram(self.compute_prog)
        GL.glDeleteProgram(self.render_prog)
        GL.glDeleteTextures(size=1, array=[self.output_image])
        GL.glDeleteBuffers(1, [self.vbo])
        GL.glDeleteVertexArrays(1, [self.vao])


if __name__ == "__main__":
    application.run(cls=SimpleCompute, title="Simple Compute Shader Example")

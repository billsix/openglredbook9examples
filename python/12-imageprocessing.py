"""12-imageprocessing — compute shader two-pass scanline derivative.

Port of ``src/12-imageprocessing/12-imageprocessing.cpp``.

Two compute dispatches in series:
  1. Reads each row of the input texture into shared memory and
     writes the per-row x-difference into ``intermediate_image``,
     transposing as it goes.
  2. Same shader runs again on the intermediate, producing the
     per-column derivative — which combined with step 1 gives an
     X+Y central-difference edge image.

Then a fullscreen quad samples ``output_image`` and draws.
"""

import ctypes
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, dds

COMPUTE_SOURCE: str = """\
#version 430 core

layout (local_size_x = 1024) in;

layout (rgba32f, binding = 0) uniform image2D input_image;
layout (rgba32f, binding = 1) uniform image2D output_image;

shared vec4 scanline[1024];

void main(void)
{
    ivec2 pos = ivec2(gl_GlobalInvocationID.xy);
    scanline[pos.x] = imageLoad(input_image, pos);
    barrier();
    imageStore(output_image, pos.yx, scanline[min(pos.x + 1, 1023)] - scanline[max(pos.x - 1, 0)]);
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

layout (binding = 0) uniform sampler2D output_image;

void main(void)
{
    color = abs(texture(output_image, vec2(1.0, -1.0) * vec2(gl_FragCoord.xy) / vec2(textureSize(output_image, 0)))) * 1.0;
}
"""


class ImageProcessing(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.compute_prog: int = common.compile_program(cs=COMPUTE_SOURCE)

        # curiosity.dds is a 1024x1024 RGBA32F DDS (FourCC 116,
        # D3DFMT_A32B32G32R32F), uploaded as the C++ vglLoadTexture does,
        # which is what makes the rgba32f image binding below legal.
        self.input_image: int = dds.upload_2d(
            common.media_path("curiosity.dds")
        )

        self.intermediate_image: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.intermediate_image)
        GL.glTexStorage2D(GL.GL_TEXTURE_2D, 8, GL.GL_RGBA32F, 1024, 1024)

        self.output_image: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.output_image)
        GL.glTexStorage2D(GL.GL_TEXTURE_2D, 8, GL.GL_RGBA32F, 1024, 1024)

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
        # Pass 1: input → intermediate
        GL.glUseProgram(self.compute_prog)
        GL.glBindImageTexture(
            0,
            self.input_image,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_READ_ONLY,
            GL.GL_RGBA32F,
        )
        GL.glBindImageTexture(
            1,
            self.intermediate_image,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_WRITE_ONLY,
            GL.GL_RGBA32F,
        )
        GL.glDispatchCompute(1, 1024, 1)
        GL.glMemoryBarrier(GL.GL_SHADER_IMAGE_ACCESS_BARRIER_BIT)

        # Pass 2: intermediate → output
        GL.glBindImageTexture(
            0,
            self.intermediate_image,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_READ_ONLY,
            GL.GL_RGBA32F,
        )
        GL.glBindImageTexture(
            1,
            self.output_image,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_WRITE_ONLY,
            GL.GL_RGBA32F,
        )
        GL.glDispatchCompute(1, 1024, 1)
        GL.glMemoryBarrier(
            GL.GL_TEXTURE_FETCH_BARRIER_BIT
        )  # imageStore -> texture(), traps §2

        GL.glActiveTexture(GL.GL_TEXTURE0)
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
        GL.glDeleteTextures(size=1, array=[self.intermediate_image])
        GL.glDeleteTextures(size=1, array=[self.input_image])
        GL.glDeleteVertexArrays(1, [self.render_vao])
        GL.glDeleteBuffers(1, [self.render_vbo])


if __name__ == "__main__":
    application.run(
        cls=ImageProcessing, title="Compute Shader Image Processing Example"
    )

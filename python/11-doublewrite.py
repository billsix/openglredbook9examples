"""11-doublewrite — image-store FS writes each fragment to two pixel
locations.

Port of ``src/11-doublewrite/11-doublewrite.cpp``. Two
images bound:

  * unit 0: a 256-entry color palette (``imageBuffer``).
  * unit 1: a 2048×2048 ``rgba32f`` image, used as the output canvas.

The fragment shader looks up its primitive ID's color from the
palette, then writes it twice into the output image — once shifted
left 200 pixels, once shifted right 200 pixels — with no normal raster
output (color masks all four channels off). A blit pass then samples
the output image and writes it to the default framebuffer.
"""

import ctypes
from typing import override

# glfw before imgui_bundle: pyglfw must bind the system GLFW, not the
# X11-only copy imgui_bundle bundles (gl-and-imgui-gotchas.md §1).
import glfw  # noqa: F401
import numpy as np
import OpenGL.GL as GL
from imgui_bundle import imgui

from redbook9 import application, common, vbm, vmath

MAX_FB_W: int = 2048
MAX_FB_H: int = 2048


class DoubleWrite(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        self.cur_w = self.window_width
        self.cur_h = self.window_height
        self._init_programs()

        # Palette TBO (256 RGBA32F entries, each ``vec4(i)``).
        self.palette_buffer: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, self.palette_buffer)
        GL.glBufferData(
            target=GL.GL_TEXTURE_BUFFER,
            size=256 * 16,
            data=None,
            usage=GL.GL_STATIC_DRAW,
        )
        self.palette_texture: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_BUFFER, self.palette_texture)
        GL.glTexBuffer(GL.GL_TEXTURE_BUFFER, GL.GL_RGBA32F, self.palette_buffer)

        palette: np.ndarray = np.zeros((256, 4), dtype=np.float32)
        for i in range(256):
            palette[i] = [i, i, i, i]
        GL.glBufferSubData(
            target=GL.GL_TEXTURE_BUFFER,
            offset=0,
            size=palette.nbytes,
            data=palette,
        )

        # Output 2D image.
        GL.glActiveTexture(GL.GL_TEXTURE0)
        self.output_texture: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.output_texture)
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST
        )
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D,
            0,
            GL.GL_RGBA32F,
            MAX_FB_W,
            MAX_FB_H,
            0,
            GL.GL_RGBA,
            GL.GL_FLOAT,
            None,
        )
        GL.glBindImageTexture(
            0,
            self.output_texture,
            0,
            GL.GL_TRUE,
            0,
            GL.GL_READ_WRITE,
            GL.GL_RGBA32F,
        )

        # The C++ clears the output via a zero-filled PBO + glTexSubImage2D
        # — but its PBO is sized for sizeof(GLuint)/pixel even though the
        # texture is RGBA32F (16 bytes/pixel), so the upload reads past
        # end of PBO. Mesa rejects this with INVALID_OPERATION (other
        # drivers tolerate it). We use glClearTexImage (4.4+) instead,
        # which clears the texture to zero with one call and no buffer
        # gymnastics.

        # Fullscreen quad VAO/VBO.
        quad: np.ndarray = np.array(
            [
                [-1.0, -1.0],
                [1.0, -1.0],
                [-1.0, 1.0],
                [1.0, 1.0],
            ],
            dtype=np.float32,
        )
        self.quad_vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.quad_vao)
        self.quad_vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.quad_vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=quad.nbytes,
            data=quad,
            usage=GL.GL_STATIC_DRAW,
        )
        GL.glVertexAttribPointer(
            index=0,
            size=2,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )
        GL.glEnableVertexAttribArray(0)

        GL.glClearDepth(1.0)
        self.object = vbm.VBObject()
        self.object.load(common.media_path("unit_pipe.vbm"))

    def _init_programs(self) -> None:
        # Read the upstream VS as-is, but use a *modified* fragment
        # shader that wraps the imageStore pair in
        # ``GL_ARB_fragment_shader_interlock``. Without it, multiple
        # overlapping fragments at the same screen pixel race on
        # imageStore and Mesa picks "winners" inconsistently across
        # frames — the visual shimmer Bill saw and called z-fighting.
        # AMD/NVIDIA proprietary drivers happen to enforce raster
        # ordering implicitly, so the C++ source doesn't need this.
        # The extension is `enable`d and `#ifdef`-guarded rather than
        # `require`d: on a driver without it (llvmpipe, the headless
        # sweep's renderer) the shader must still compile, degrading to
        # exactly the upstream's unordered behaviour. Found 2026-09-09
        # when this demo was the only redbook9 CRASH in the headless
        # sweep -- see tasks/reference/ports/headless-verification.md.
        with open(
            common.media_path("shaders", "doublewrite", "double_write.vs.glsl"),
            mode="r",
        ) as f:
            vs_source: str = f.read()

        fs_source: str = """\
#version 430 core

// `enable`, not `require`: the interlock is a port-only fix for Mesa's
// radeonsi, which supports it. Drivers without it (llvmpipe, some Intel
// stacks) fall back to the upstream C++ behaviour -- the racy but valid
// unordered imageStore -- instead of refusing to compile the shader.
#extension GL_ARB_fragment_shader_interlock : enable
#ifdef GL_ARB_fragment_shader_interlock
layout (pixel_interlock_ordered) in;
#endif

// Buffer containing a palette of colors to be used to mark primitives by ID
layout (binding = 0, rgba32f) uniform imageBuffer colors;

// The buffer that we will write to
layout (binding = 1, rgba32f) uniform image2D output_buffer;

out vec4 color;

void main(void)
{
    // Load a color from the palette buffer based on primitive ID % 256
    vec4 col = imageLoad(colors, gl_PrimitiveID & 255);

    // Per-pixel ordered region: ensures overlapping fragments at the
    // same screen pixel write in primitive-emit order (a port-only
    // change from the upstream C++ — see _init_programs comment).
#ifdef GL_ARB_fragment_shader_interlock
    beginInvocationInterlockARB();
#endif
    imageStore(output_buffer, ivec2(gl_FragCoord.xy) - ivec2(200, 0), col);
    imageStore(output_buffer, ivec2(gl_FragCoord.xy) + ivec2(200, 0), col);
#ifdef GL_ARB_fragment_shader_interlock
    endInvocationInterlockARB();
#endif
}
"""

        self.scene_prog: int = common.compile_program(
            vs=vs_source, fs=fs_source
        )
        self.scene_model: int = GL.glGetUniformLocation(
            program=self.scene_prog, name="model_matrix"
        )
        self.scene_view: int = GL.glGetUniformLocation(
            program=self.scene_prog, name="view_matrix"
        )
        self.scene_proj: int = GL.glGetUniformLocation(
            program=self.scene_prog, name="projection_matrix"
        )
        self.scene_aspect: int = GL.glGetUniformLocation(
            program=self.scene_prog, name="aspect"
        )
        self.scene_time: int = GL.glGetUniformLocation(
            program=self.scene_prog, name="time"
        )

        self.resolve_prog: int = common.compile_program_from_files(
            vs=common.media_path("shaders", "doublewrite", "blit.vs.glsl"),
            fs=common.media_path("shaders", "doublewrite", "blit.fs.glsl"),
        )

    @override
    def resize(self, width: int, height: int) -> None:
        self.cur_w = width
        self.cur_h = height
        self.aspect = float(height) / float(max(1, width))
        GL.glViewport(0, 0, width, height)
        self.window_width = width
        self.window_height = height

    @override
    def display(self, auto_redraw: bool = True) -> None:

        t: float = float(self.app_time() & 0xFFFFF) / float(0x3FFF)

        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_CULL_FACE)

        GL.glClearColor(0.0, 0.0, 0.0, 0.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        # Bind palette as image unit 0 (read-only).
        GL.glBindImageTexture(
            0,
            self.palette_texture,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_READ_ONLY,
            GL.GL_RGBA32F,
        )

        # Clear the output image to all-zeros (replaces the C++ PBO
        # upload — see the initialize() comment for context). The
        # following barrier ensures the cleared values are visible to
        # the imageStore in the scene fragment shader.
        GL.glClearTexImage(
            self.output_texture, 0, GL.GL_RGBA, GL.GL_FLOAT, None
        )
        GL.glMemoryBarrier(GL.GL_TEXTURE_UPDATE_BARRIER_BIT)

        # Bind output as image unit 1 (read-write).
        GL.glBindImageTexture(
            1,
            self.output_texture,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_READ_WRITE,
            GL.GL_RGBA32F,
        )

        GL.glUseProgram(self.scene_prog)
        m: np.ndarray = (
            vmath.translate(x=0.0, y=0.0, z=-15.0)
            @ vmath.rotate(angle_degrees=t * 360.0, ax=0, ay=0, az=1)
            @ vmath.rotate(angle_degrees=t * 435.0, ax=0, ay=1, az=0)
            @ vmath.rotate(angle_degrees=t * 275.0, ax=1, ay=0, az=0)
        )
        v: np.ndarray = vmath.identity()
        p: np.ndarray = vmath.frustum(
            left=-1.0,
            right=1.0,
            bottom=self.aspect,
            top=-self.aspect,
            near=1.0,
            far=40.0,
        )
        vmath.upload(location=self.scene_model, mat=m)
        vmath.upload(location=self.scene_view, mat=v)
        vmath.upload(location=self.scene_proj, mat=p)

        GL.glColorMask(GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE)
        self.object.render(0, 4 * 4 * 4)
        GL.glColorMask(GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE)

        # The C++ omits this barrier between scene-imageStore and
        # resolve-imageLoad; AMD/NVIDIA proprietary drivers tolerate the
        # missing barrier (implicit synchronization between programs
        # binding the same image), Mesa does not — without it the
        # resolve sees a partially-flushed view and the output looks
        # like z-fighting.
        GL.glMemoryBarrier(GL.GL_SHADER_IMAGE_ACCESS_BARRIER_BIT)

        # Resolve: bind output as image unit 0, read-only.
        GL.glBindImageTexture(
            0,
            self.output_texture,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_READ_ONLY,
            GL.GL_RGBA32F,
        )
        GL.glBindVertexArray(self.quad_vao)
        GL.glUseProgram(self.resolve_prog)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)

        super().display(auto_redraw)

    @override
    def draw_controls(self) -> None:
        # The C++'s R key as a widget (rules §3); R stays as the accelerator.
        if imgui.button("Reload shaders (R)"):
            self._init_programs()

    @override
    def on_key(self, key: int, scancode: int, action: int, mods: int) -> None:
        if action == self.PRESS and key == self.KEY_R:
            self._init_programs()
            return
        super().on_key(key, scancode, action, mods)

    @override
    def finalize(self) -> None:
        GL.glDeleteProgram(self.scene_prog)
        GL.glDeleteProgram(self.resolve_prog)
        GL.glDeleteBuffers(1, [self.quad_vbo])
        GL.glDeleteVertexArrays(1, [self.quad_vao])
        GL.glDeleteBuffers(1, [self.palette_buffer])
        GL.glDeleteTextures(size=1, array=[self.palette_texture])
        GL.glDeleteTextures(size=1, array=[self.output_texture])
        self.object.free()


if __name__ == "__main__":
    application.run(cls=DoubleWrite, title="Double Write Example")

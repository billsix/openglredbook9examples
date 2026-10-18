"""11-overdrawcount — counts how many times each pixel is shaded.

Port of ``src/11-overdrawcount/11-overdrawcount.cpp``. Same
shape as 11-doublewrite but the FS does ``imageAtomicAdd`` on a
``r32ui`` image at the fragment's window-space coords; the resolve
pass reads that integer and converts to a hot-cold colormap. Disable
color-write while drawing the scene so only the image-load-store
side-effects remain.
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


class OverdrawCount(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        self.cur_w = self.window_width
        self.cur_h = self.window_height

        self._init_programs()

        self.overdraw_buffer: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.overdraw_buffer)
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST
        )
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D,
            0,
            GL.GL_R32UI,
            MAX_FB_W,
            MAX_FB_H,
            0,
            GL.GL_RED_INTEGER,
            GL.GL_UNSIGNED_INT,
            None,
        )
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        # Note: C++ uses a zero PBO + glTexSubImage2D to clear the
        # counter each frame; we use glClearTexImage (4.4+) for the
        # same effect. See 11-doublewrite for the size-mismatch
        # rationale.

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
        self.scene_prog: int = common.compile_program_from_files(
            vs=common.media_path(
                "shaders", "overdrawcount", "overdraw_count.vs.glsl"
            ),
            fs=common.media_path(
                "shaders", "overdrawcount", "overdraw_count.fs.glsl"
            ),
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
        self.resolve_prog: int = common.compile_program_from_files(
            vs=common.media_path("shaders", "overdrawcount", "blit.vs.glsl"),
            fs=common.media_path("shaders", "overdrawcount", "blit.fs.glsl"),
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

        # Clear the overdraw counter to zero. The barrier ensures the
        # cleared values are visible to the imageAtomicAdd in the scene
        # fragment shader.
        GL.glClearTexImage(
            self.overdraw_buffer, 0, GL.GL_RED_INTEGER, GL.GL_UNSIGNED_INT, None
        )
        GL.glMemoryBarrier(GL.GL_TEXTURE_UPDATE_BARRIER_BIT)

        GL.glBindImageTexture(
            0,
            self.overdraw_buffer,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_READ_WRITE,
            GL.GL_R32UI,
        )

        GL.glUseProgram(self.scene_prog)
        m: np.ndarray = (
            vmath.translate(x=0.0, y=0.0, z=-20.0)
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
        self.object.render(0, 8 * 8 * 8)
        GL.glColorMask(GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE)

        # Mesa needs an explicit barrier between the imageAtomicAdd's
        # in scene_prog and the imageLoad in resolve_prog. Same lesson
        # as 11-doublewrite.
        GL.glMemoryBarrier(GL.GL_SHADER_IMAGE_ACCESS_BARRIER_BIT)

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
        GL.glDeleteTextures(size=1, array=[self.overdraw_buffer])
        self.object.free()


if __name__ == "__main__":
    application.run(cls=OverdrawCount, title="Overdraw Count Example")

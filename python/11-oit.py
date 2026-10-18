"""11-oit — order-independent transparency via per-pixel linked lists.

Port of ``src/11-oit/11-oit.cpp``. The classic A-buffer
technique:

  * pass 1 (build): each transparent fragment ``imageAtomicAdd``s a
    counter and writes its (color, depth, prev) tuple into a TBO.
    The head-pointer image is updated atomically so the new node
    becomes the list's head.
  * pass 2 (resolve): a fullscreen quad walks the linked list per
    pixel, sorts it by depth, and blends back-to-front.

Resources held GPU-side: head_pointer_texture (R32UI),
atomic_counter_buffer (1 uint), linked_list_texture (RGBA32UI TBO,
16 bytes per ``uvec4`` node × 3 nodes per pixel × 2048²).
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


class OITDemo(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        self.cur_w = self.window_width
        self.cur_h = self.window_height

        self._init_programs()

        # Head-pointer 2D image.
        GL.glActiveTexture(GL.GL_TEXTURE0)
        self.head_tex: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.head_tex)
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
        GL.glBindImageTexture(
            0, self.head_tex, 0, GL.GL_TRUE, 0, GL.GL_READ_WRITE, GL.GL_R32UI
        )

        # Note: C++ uses a zero PBO + glTexSubImage2D to clear the
        # head-pointer each frame; we use glClearTexImage (4.4+).
        # See 11-doublewrite for the rationale.

        # Atomic counter (single uint).
        self.atomic_buffer: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ATOMIC_COUNTER_BUFFER, self.atomic_buffer)
        GL.glBufferData(
            target=GL.GL_ATOMIC_COUNTER_BUFFER,
            size=4,
            data=None,
            usage=GL.GL_DYNAMIC_COPY,
        )

        # Linked-list TBO. 3 RGBA32UI per pixel — depth × ~3 transparent
        # layers max with 16 bytes per node.
        self.list_buffer: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, self.list_buffer)
        GL.glBufferData(
            target=GL.GL_TEXTURE_BUFFER,
            size=MAX_FB_W * MAX_FB_H * 3 * 16,
            data=None,
            usage=GL.GL_DYNAMIC_COPY,
        )
        GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, 0)
        self.list_tex: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_BUFFER, self.list_tex)
        GL.glTexBuffer(GL.GL_TEXTURE_BUFFER, GL.GL_RGBA32UI, self.list_buffer)
        GL.glBindTexture(GL.GL_TEXTURE_BUFFER, 0)
        GL.glBindImageTexture(
            1,
            self.list_tex,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_WRITE_ONLY,
            GL.GL_RGBA32UI,
        )

        # The C++ uses an oddly off-center quad: x goes 0..1 instead of
        # -1..1 — same here for visual parity. (Demonstrates that the
        # resolve sees only the right half.)
        quad: np.ndarray = np.array(
            [
                [-0.0, -1.0],
                [1.0, -1.0],
                [-0.0, 1.0],
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
            vs=common.media_path("shaders", "oit", "build_lists.vs.glsl"),
            fs=common.media_path("shaders", "oit", "build_lists.fs.glsl"),
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
            vs=common.media_path("shaders", "oit", "resolve_lists.vs.glsl"),
            fs=common.media_path("shaders", "oit", "resolve_lists.fs.glsl"),
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

        # Reset atomic counter to 0.
        GL.glBindBufferBase(GL.GL_ATOMIC_COUNTER_BUFFER, 0, self.atomic_buffer)
        zero: np.ndarray = np.zeros(1, dtype=np.uint32)
        GL.glBufferSubData(
            target=GL.GL_ATOMIC_COUNTER_BUFFER, offset=0, size=4, data=zero
        )

        # Clear head pointer image to zero. Barrier ensures the cleared
        # texels and the reset atomic counter are visible to the
        # imageAtomicAdd in the scene fragment shader.
        GL.glClearTexImage(
            self.head_tex, 0, GL.GL_RED_INTEGER, GL.GL_UNSIGNED_INT, None
        )
        GL.glMemoryBarrier(
            GL.GL_TEXTURE_UPDATE_BARRIER_BIT | GL.GL_BUFFER_UPDATE_BARRIER_BIT  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
        )

        GL.glBindImageTexture(
            0, self.head_tex, 0, GL.GL_FALSE, 0, GL.GL_READ_WRITE, GL.GL_R32UI
        )
        GL.glBindImageTexture(
            1,
            self.list_tex,
            0,
            GL.GL_FALSE,
            0,
            GL.GL_WRITE_ONLY,
            GL.GL_RGBA32UI,
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

        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        self.object.render(0, 8 * 8 * 8)
        GL.glDisable(GL.GL_BLEND)

        # Mesa needs an explicit barrier between the scene's
        # imageStore/imageAtomicAdd writes (head pointer + linked-list
        # buffer + atomic counter) and the resolve pass's imageLoad
        # walk through the lists. Same lesson as 11-doublewrite.
        GL.glMemoryBarrier(
            GL.GL_SHADER_IMAGE_ACCESS_BARRIER_BIT  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int
            | GL.GL_ATOMIC_COUNTER_BARRIER_BIT
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
        GL.glDeleteBuffers(1, [self.atomic_buffer])
        GL.glDeleteBuffers(1, [self.list_buffer])
        GL.glDeleteTextures(size=1, array=[self.head_tex])
        GL.glDeleteTextures(size=1, array=[self.list_tex])
        self.object.free()


if __name__ == "__main__":
    application.run(cls=OITDemo, title="Order Independent Transparency")

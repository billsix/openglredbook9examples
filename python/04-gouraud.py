"""04-gouraud — per-vertex color (Gouraud-style) interpolated to fragments.

Port of ``src/04-gouraud/04-gouraud.cpp``. The C++ side
interleaves a per-vertex ``GLubyte color[4]`` with ``GLfloat
position[2]`` in a single struct; the vertex attribute uses
``GL_UNSIGNED_BYTE`` with ``normalize=GL_TRUE``. We reproduce that
exactly so the byte layout in the VBO matches.
"""

import ctypes
from typing import override

# glfw before imgui_bundle: pyglfw must bind the system GLFW, not the
# X11-only copy imgui_bundle bundles (gl-and-imgui-gotchas.md §1).
import glfw  # noqa: F401
import numpy as np
import OpenGL.GL as GL
from imgui_bundle import imgui

from redbook9 import application, common

VPOSITION: int = 0
VCOLOR: int = 1
NUM_VERTICES: int = 6
STRIDE: int = 4 + 8  # 4 bytes color (UB4) + 8 bytes position (vec2)


class Gouraud(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)

        # Build the interleaved buffer manually as raw bytes so the
        # offsets line up with the C++ struct.
        verts = bytearray()
        records = [
            (255, 0, 0, 255, -0.90, -0.90),
            (0, 255, 0, 255, 0.85, -0.90),
            (0, 0, 255, 255, -0.90, 0.85),
            (10, 10, 10, 255, 0.90, -0.85),
            (100, 100, 100, 255, 0.90, 0.90),
            (255, 255, 255, 255, -0.85, 0.90),
        ]
        for r, g, b, a, x, y in records:
            verts.extend(bytes([r, g, b, a]))
            verts.extend(np.array([x, y], dtype=np.float32).tobytes())

        self.vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=len(verts),
            data=bytes(verts),
            usage=GL.GL_STATIC_DRAW,
        )

        # The same files the C++ ShaderInfo table names.
        self.program: int = common.compile_program_from_files(
            vs=common.media_path("shaders", "gouraud", "gouraud.vert"),
            fs=common.media_path("shaders", "gouraud", "gouraud.frag"),
        )
        GL.glUseProgram(self.program)

        GL.glVertexAttribPointer(
            index=VCOLOR,
            size=4,
            type=GL.GL_UNSIGNED_BYTE,
            normalized=GL.GL_TRUE,
            stride=STRIDE,
            pointer=ctypes.c_void_p(0),
        )
        GL.glVertexAttribPointer(
            index=VPOSITION,
            size=2,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=STRIDE,
            pointer=ctypes.c_void_p(4),
        )
        GL.glEnableVertexAttribArray(VCOLOR)
        GL.glEnableVertexAttribArray(VPOSITION)

        self._mode: common.GLenum = GL.GL_FILL

    @override
    def display(self, auto_redraw: bool = True) -> None:

        GL.glClearColor(0.0, 0.0, 0.0, 0.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, NUM_VERTICES)
        super().display(auto_redraw)

    @override
    def draw_controls(self) -> None:
        # The C++'s M key as a widget (rules §3); M stays as the accelerator.
        changed, wire = imgui.checkbox(
            label="Wireframe (M)", v=self._mode == GL.GL_LINE
        )
        if changed:
            self._mode = GL.GL_LINE if wire else GL.GL_FILL
            GL.glPolygonMode(GL.GL_FRONT_AND_BACK, self._mode)

    @override
    def on_key(self, key: int, scancode: int, action: int, mods: int) -> None:
        if action == self.PRESS and key == self.KEY_M:
            self._mode = GL.GL_LINE if self._mode == GL.GL_FILL else GL.GL_FILL
            GL.glPolygonMode(GL.GL_FRONT_AND_BACK, self._mode)
            return
        super().on_key(key, scancode, action, mods)

    @override
    def finalize(self) -> None:
        GL.glDeleteBuffers(1, [self.vbo])
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteProgram(self.program)


if __name__ == "__main__":
    application.run(cls=Gouraud, title="Gouraud Example")

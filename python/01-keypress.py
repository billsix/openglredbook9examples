"""01-keypress — adds an on_key override to switch fill / wireframe.

Port of ``src/01-keypress/01-keypress.cpp``. Same geometry as
01-triangles, but pressing M toggles between ``GL_FILL`` and ``GL_LINE``
polygon mode.
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
NUM_VERTICES: int = 6


class KeyPress(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.vao: int = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)

        vertices: np.ndarray = np.array(
            [
                [-0.90, -0.90],
                [0.85, -0.90],
                [-0.90, 0.85],
                [0.90, -0.85],
                [0.90, 0.90],
                [-0.85, 0.90],
            ],
            dtype=np.float32,
        )

        self.vbo: int = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=vertices.nbytes,
            data=vertices,
            usage=GL.GL_STATIC_DRAW,
        )

        # The same files the C++ ShaderInfo table names.
        self.program: int = common.compile_program_from_files(
            vs=common.media_path("shaders", "keypress", "keypress.vert"),
            fs=common.media_path("shaders", "keypress", "keypress.frag"),
        )

        GL.glUseProgram(self.program)
        GL.glVertexAttribPointer(
            index=VPOSITION,
            size=2,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )
        GL.glEnableVertexAttribArray(VPOSITION)

        # Toggled by 'M'.
        self._mode: common.GLenum = GL.GL_FILL

    @override
    def display(self, auto_redraw: bool = True) -> None:

        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        GL.glBindVertexArray(self.vao)
        GL.glUseProgram(self.program)
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
    application.run(cls=KeyPress, title="Key Press Example")

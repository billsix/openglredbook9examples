"""04-shadowmap — depth-FBO based shadow mapping.

Port of ``src/04-shadowmap/04-shadowmap.cpp``. Two passes:

  1. **Depth pass.** Render the scene from the moving light's POV into
     a 2048×2048 ``GL_DEPTH_COMPONENT32`` texture attached to an FBO.
  2. **Color pass.** Render the scene from the camera, comparing each
     fragment's projected light-space depth to the shadow texture via
     a ``sampler2DShadow`` + ``textureProj`` lookup.

The "scale-bias" matrix maps clip-space [-1,1] to texture-space [0,1].
"""

import ctypes
import math
from typing import override

import numpy as np
import OpenGL.GL as GL

from redbook9 import application, common, vbm, vmath

FRUSTUM_DEPTH: float = 800.0
DEPTH_TEXTURE_SIZE: int = 2048


class ShadowMapExample(application.Application):
    @override
    def initialize(self, title: str | None = None) -> None:
        super().initialize(title)

        self.aspect = 1.0
        self.cur_w = self.window_width
        self.cur_h = self.window_height

        self.render_light_prog: int = common.compile_program_from_files(
            vs=common.media_path(
                "shaders", "shadowmap", "shadowmap_shadow.vs.glsl"
            ),
            fs=common.media_path(
                "shaders", "shadowmap", "shadowmap_shadow.fs.glsl"
            ),
        )
        self.u_light_mvp: int = GL.glGetUniformLocation(
            program=self.render_light_prog, name="model_view_projection_matrix"
        )

        self.render_scene_prog: int = common.compile_program_from_files(
            vs=common.media_path(
                "shaders", "shadowmap", "shadowmap_scene.vs.glsl"
            ),
            fs=common.media_path(
                "shaders", "shadowmap", "shadowmap_scene.fs.glsl"
            ),
        )

        # Cache uniform locations.
        def uloc(name: str) -> int:
            return GL.glGetUniformLocation(
                program=self.render_scene_prog, name=name
            )

        self.u_model = uloc("model_matrix")
        self.u_view = uloc("view_matrix")
        self.u_proj = uloc("projection_matrix")
        self.u_shadow = uloc("shadow_matrix")
        self.u_light_pos = uloc("light_position")
        self.u_mat_ambient = uloc("material_ambient")
        self.u_mat_diffuse = uloc("material_diffuse")
        self.u_mat_specular = uloc("material_specular")
        self.u_mat_spec_pwr = uloc("material_specular_power")

        GL.glUseProgram(self.render_scene_prog)
        GL.glUniform1i(uloc("depth_texture"), 0)

        # Depth texture.
        self.depth_texture: int = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.depth_texture)
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D,
            0,
            GL.GL_DEPTH_COMPONENT32,
            DEPTH_TEXTURE_SIZE,
            DEPTH_TEXTURE_SIZE,
            0,
            GL.GL_DEPTH_COMPONENT,
            GL.GL_FLOAT,
            None,
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D,
            GL.GL_TEXTURE_COMPARE_MODE,
            GL.GL_COMPARE_REF_TO_TEXTURE,
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_COMPARE_FUNC, GL.GL_LEQUAL
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE
        )
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

        # Depth-only FBO.
        self.depth_fbo: int = GL.glGenFramebuffers(1)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.depth_fbo)
        GL.glFramebufferTexture(
            GL.GL_FRAMEBUFFER, GL.GL_DEPTH_ATTACHMENT, self.depth_texture, 0
        )
        GL.glDrawBuffer(GL.GL_NONE)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)

        # Ground plane geometry. position(vec4) then normal(vec3),
        # split-buffer style (matches C++).
        ground_positions: np.ndarray = np.array(
            [
                [-500.0, -50.0, -500.0, 1.0],
                [-500.0, -50.0, 500.0, 1.0],
                [500.0, -50.0, 500.0, 1.0],
                [500.0, -50.0, -500.0, 1.0],
            ],
            dtype=np.float32,
        )
        ground_normals: np.ndarray = np.array(
            [
                [0.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=np.float32,
        )

        self.ground_vao: int = GL.glGenVertexArrays(1)
        self.ground_vbo: int = GL.glGenBuffers(1)
        GL.glBindVertexArray(self.ground_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.ground_vbo)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=ground_positions.nbytes + ground_normals.nbytes,
            data=None,
            usage=GL.GL_STATIC_DRAW,
        )
        GL.glBufferSubData(
            target=GL.GL_ARRAY_BUFFER,
            offset=0,
            size=ground_positions.nbytes,
            data=ground_positions,
        )
        GL.glBufferSubData(
            target=GL.GL_ARRAY_BUFFER,
            offset=ground_positions.nbytes,
            size=ground_normals.nbytes,
            data=ground_normals,
        )
        GL.glVertexAttribPointer(
            index=0,
            size=4,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(0),
        )
        GL.glVertexAttribPointer(
            index=1,
            size=3,
            type=GL.GL_FLOAT,
            normalized=GL.GL_FALSE,
            stride=0,
            pointer=ctypes.c_void_p(ground_positions.nbytes),
        )
        GL.glEnableVertexAttribArray(0)
        GL.glEnableVertexAttribArray(1)

        self.object = vbm.VBObject()
        self.object.load(common.media_path("armadillo_low.vbm"))

    @override
    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        self.cur_w = max(1, width)
        self.cur_h = max(1, height)
        self.aspect = float(self.cur_h) / float(self.cur_w)

    def _draw_scene(self, depth_only: bool) -> None:
        if not depth_only:
            GL.glUniform3fv(self.u_mat_ambient, 1, [0.1, 0.0, 0.2])
            GL.glUniform3fv(self.u_mat_diffuse, 1, [0.3, 0.2, 0.8])
            GL.glUniform3fv(self.u_mat_specular, 1, [1.0, 1.0, 1.0])
            GL.glUniform1f(self.u_mat_spec_pwr, 25.0)
        self.object.render()

        if not depth_only:
            GL.glUniform3fv(self.u_mat_ambient, 1, [0.1, 0.1, 0.1])
            GL.glUniform3fv(self.u_mat_diffuse, 1, [0.1, 0.5, 0.1])
            GL.glUniform3fv(self.u_mat_specular, 1, [0.1, 0.1, 0.1])
            GL.glUniform1f(self.u_mat_spec_pwr, 3.0)
        GL.glBindVertexArray(self.ground_vao)
        GL.glDrawArrays(GL.GL_TRIANGLE_FAN, 0, 4)
        GL.glBindVertexArray(0)

    @override
    def display(self, auto_redraw: bool = True) -> None:
        t: float = float(self.app_time() & 0xFFFF) / float(0xFFFF)

        light_position: np.ndarray = np.array(
            [
                math.sin(t * 6.0 * math.pi) * 300.0,
                200.0,
                math.cos(t * 4.0 * math.pi) * 100.0 + 250.0,
            ],
            dtype=np.float32,
        )

        GL.glEnable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)

        scene_model: np.ndarray = vmath.rotate(
            angle_degrees=t * 720.0, ax=0, ay=1, az=0
        )
        scene_view: np.ndarray = vmath.translate(x=0.0, y=0.0, z=-300.0)
        scene_proj: np.ndarray = vmath.frustum(
            left=-1.0,
            right=1.0,
            bottom=-self.aspect,
            top=self.aspect,
            near=1.0,
            far=FRUSTUM_DEPTH,
        )

        # vmath stores the C++ ``mat4(col0, col1, col2, col3)`` as
        # column-major. ``scale_bias`` is the standard NDC→tex transform.
        scale_bias: np.ndarray = np.array(
            [
                [0.5, 0.0, 0.0, 0.5],
                [0.0, 0.5, 0.0, 0.5],
                [0.0, 0.0, 0.5, 0.5],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float32,
        )

        light_view: np.ndarray = vmath.lookat(
            eye=light_position,
            center=np.array([0, 0, 0], dtype=np.float32),
            up=np.array([0, 1, 0], dtype=np.float32),
        )
        light_proj: np.ndarray = vmath.frustum(
            left=-1.0,
            right=1.0,
            bottom=-1.0,
            top=1.0,
            near=1.0,
            far=FRUSTUM_DEPTH,
        )

        # ---- Depth pass -------------------------------------------
        GL.glUseProgram(self.render_light_prog)
        light_mvp = light_proj @ light_view @ scene_model
        vmath.upload(location=self.u_light_mvp, mat=light_mvp)

        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.depth_fbo)
        GL.glViewport(0, 0, DEPTH_TEXTURE_SIZE, DEPTH_TEXTURE_SIZE)
        GL.glClearDepth(1.0)
        GL.glClear(GL.GL_DEPTH_BUFFER_BIT)
        GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glPolygonOffset(2.0, 4.0)
        self._draw_scene(depth_only=True)
        GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)

        # ---- Color pass -------------------------------------------
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
        GL.glViewport(0, 0, self.cur_w, self.cur_h)

        GL.glUseProgram(self.render_scene_prog)
        GL.glClear(GL.GL_DEPTH_BUFFER_BIT | GL.GL_COLOR_BUFFER_BIT)  # ty: ignore[unsupported-operator]  # PyOpenGL's Constant lacks __or__ in ty's view; at runtime `|` on GL bitmask constants yields a plain int

        vmath.upload(location=self.u_model, mat=scene_model)
        vmath.upload(location=self.u_view, mat=scene_view)
        vmath.upload(location=self.u_proj, mat=scene_proj)
        vmath.upload(
            location=self.u_shadow, mat=scale_bias @ light_proj @ light_view
        )
        GL.glUniform3fv(self.u_light_pos, 1, light_position)

        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.depth_texture)

        self._draw_scene(depth_only=False)

        super().display(auto_redraw)

    @override
    def finalize(self) -> None:
        GL.glDeleteProgram(self.render_light_prog)
        GL.glDeleteProgram(self.render_scene_prog)
        GL.glDeleteBuffers(1, [self.ground_vbo])
        GL.glDeleteVertexArrays(1, [self.ground_vao])
        GL.glDeleteFramebuffers(1, [self.depth_fbo])
        GL.glDeleteTextures(size=1, array=[self.depth_texture])
        self.object.free()


if __name__ == "__main__":
    application.run(cls=ShadowMapExample, title="Shadow Mapping Example")

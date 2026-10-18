"""Shared helpers for the OpenGL Red Book 9e Python ports.

1. Re-exports the window/menubar/camera helpers from the vendored
   ``window.py`` (see the banner in that file) so demos can
   ``import common`` and get ``WindowState``, ``draw_menubar``,
   ``Camera``, etc.

2. Adds shader-compile helpers: ``compile_shader`` for one stage,
   ``compile_program`` for a vs/fs (or any combination) pair, and
   file-reading wrappers. These mirror the role of
   ``LoadShaders.cpp`` + ``vglAttachShaderSource`` in the C++
   framework.

3. Adds ``MEDIA_DIR`` — resolved at import time. Demos that load
   textures or .vbm models read from there.
"""

from __future__ import annotations

import ctypes
import os
from typing import Iterable, Optional, Sequence

import OpenGL.GL as GL
from OpenGL.constant import Constant

from . import window

#: A value OpenGL accepts where it wants an enum -- PyOpenGL constants
#: resolve to `OpenGL.constant.Constant`, not `int`, so a plain `int`
#: annotation rejects them. Same house pattern as
#: src/modelviewprojection/wxapp.py.
GLenum = int | Constant

_HERE = os.path.dirname(os.path.abspath(__file__))

# Re-export the vendored window/menubar/camera helpers (from window.py).
Camera = window.Camera
SceneObject = window.SceneObject
WindowState = window.WindowState
apply_camera = window.apply_camera
bind_camera_inputs = window.bind_camera_inputs
draw_camera_controls = window.draw_camera_controls
draw_menubar = window.draw_menubar
init_imgui = window.init_imgui
resolve_default_window_size = window.resolve_default_window_size
toggle_fullscreen = window.toggle_fullscreen
update_camera = window.update_camera


# ---------------------------------------------------------------------------
# Media-directory resolution
# ---------------------------------------------------------------------------
#
# Resolution order:
#   1. ``$REDBOOK9_MEDIA`` env var, if set and a directory (override).
#   2. ``<repo>/bin/media`` -- one directory up from this ``python/`` port,
#      the C sources' own media. This is the normal case and needs no env
#      var, in the container or on a host checkout.
#   3. ``<port>/bin/media`` -- a copy dropped into the port directory.
#   4. A sibling/cousin checkout named ``openglredbook9``/``redbook9``, then a
#      few common dev-box locations.
# The media is NOT duplicated in the port: it is referenced from the C repo's
# single tracked copy (~266 MB of textures/meshes/shaders).


def _find_media_dir() -> tuple[str | None, list[str]]:
    """Returns ``(path, tried_paths)``. ``path`` is the resolved media
    directory or ``None`` when nothing matched; ``tried_paths`` is the
    list of every concrete path we checked, useful for error messages.
    """
    tried: list[str] = []
    env = os.environ.get("REDBOOK9_MEDIA")
    if env:
        tried.append(f"$REDBOOK9_MEDIA={env}")
        if os.path.isdir(env):
            return os.path.abspath(env), tried

    # Normal case: this port lives at ``<repo>/python/`` and the C
    # sources' media is tracked at ``<repo>/bin/media`` -- one directory
    # up. Reference it here rather than carrying a copy, so the ~266 MB
    # of textures/meshes/shaders lives in exactly one place. Resolves both
    # in the container (repo mounted with python/ + bin/ siblings) and on
    # a host checkout.
    in_repo: str = os.path.join(os.path.dirname(_HERE), "bin", "media")
    tried.append(in_repo)
    if os.path.isdir(in_repo):
        return in_repo, tried

    # Fallback: a copy dropped straight into the port directory.
    in_port: str = os.path.join(_HERE, "bin", "media")
    tried.append(in_port)
    if os.path.isdir(in_port):
        return in_port, tried

    # Walk up looking for a sibling/cousin checkout of the C repo under
    # either name it gets cloned as.
    current = _HERE
    for _ in range(12):
        parent = os.path.dirname(current)
        if parent == current:
            break
        for name in ("openglredbook9", "redbook9"):
            candidate: str = os.path.join(parent, name, "bin", "media")
            tried.append(candidate)
            if os.path.isdir(candidate):
                return candidate, tried
        current = parent

    # A few extra plausible locations on a typical dev box.
    home = os.path.expanduser("~")
    extras: list[str] = [
        os.path.join(home, "opt", "openglredbook9", "bin", "media"),
        os.path.join(home, "opt", "redbook9", "bin", "media"),
        os.path.join(home, "src", "redbook9", "bin", "media"),
        os.path.join(home, "redbook9", "bin", "media"),
        "/openglredbook9/bin/media",
        "/redbook9/bin/media",
    ]
    for candidate in extras:
        if candidate not in tried:
            tried.append(candidate)
            if os.path.isdir(candidate):
                return candidate, tried

    return None, tried


MEDIA_DIR, _MEDIA_TRIED = _find_media_dir()


def media_path(*relative: str) -> str:
    """Join ``MEDIA_DIR`` with the given relative components. Raises
    ``FileNotFoundError`` if no media directory was found, listing
    every path we checked so the user can see why."""
    if MEDIA_DIR is None:
        tried = "\n    ".join(_MEDIA_TRIED) if _MEDIA_TRIED else "(none)"
        raise FileNotFoundError(
            "Red Book 9e media directory not found.\n\n"
            "Tried in order:\n    " + tried + "\n\n"
            "Fix: point REDBOOK9_MEDIA at your redbook9 source's "
            "bin/media directory, e.g.:\n"
            "    export REDBOOK9_MEDIA=/path/to/redbook9/bin/media\n"
            "or symlink:\n"
            "    ln -s /path/to/redbook9 ~/redbook9\n"
        )
    return os.path.join(MEDIA_DIR, *relative)


# ---------------------------------------------------------------------------
# Shader compilation
# ---------------------------------------------------------------------------


class ShaderError(RuntimeError):
    """Raised when GLSL compilation or program linking fails. The
    message is the driver's info log so students see exactly what the
    GLSL compiler said."""


def _ensure_binding_qualifier_version(source: str) -> str:
    """If the shader uses ``layout(binding = N)`` but declares a
    ``#version`` lower than 420, bump to 420. Mesa rejects the binding
    qualifier under 4.10. (Lesson from the v7 port.)"""
    if "binding" not in source:
        return source
    import re

    m = re.search(r"^\s*#version\s+(\d+)\s+core", source, flags=re.MULTILINE)
    if not m:
        return source
    ver: int = int(m.group(1))
    if 100 <= ver < 420:
        return re.sub(
            r"^(\s*#version\s+)\d+(\s+core)",
            r"\g<1>420\g<2>",
            source,
            count=1,
            flags=re.MULTILINE,
        )
    return source


def compile_shader(source: str, shader_type: GLenum) -> int:
    """Compile a single GLSL shader stage. Returns the shader name on
    success, raises ``ShaderError`` with the info log on failure."""
    source = _ensure_binding_qualifier_version(source)
    shader: int = GL.glCreateShader(shader_type)
    GL.glShaderSource(shader, source)
    GL.glCompileShader(shader)
    status: int = GL.glGetShaderiv(shader=shader, pname=GL.GL_COMPILE_STATUS)
    if not status:
        log = GL.glGetShaderInfoLog(shader).decode(errors="replace")
        GL.glDeleteShader(shader)
        raise ShaderError(f"shader compile failed: {log}")
    return shader


def compile_shader_from_file(path: str, shader_type: GLenum) -> int:
    # errors="replace": upstream shaders are ASCII except for the odd Latin-1
    # byte in a copyright comment (v7's rgtc/rgtccompress.cs.glsl carries a
    # 0xA9 (c)); the C++ handed the compiler raw bytes, so decoding must not
    # raise. Same rule as v7's common, kept identical on purpose.
    with open(path, mode="r", encoding="utf-8", errors="replace") as f:
        return compile_shader(source=f.read(), shader_type=shader_type)


def link_program(
    shaders: Iterable[int],
    *,
    delete_shaders: bool = True,
    tf_varyings: Optional[Sequence[str]] = None,
    tf_buffer_mode: GLenum | None = None,
) -> int:
    """Link a program from already-compiled shader objects. Detaches
    and (by default) deletes the shaders afterward — same convention
    as v7's ``link_program``.

    Optional ``tf_varyings`` enables transform feedback before linking;
    pass varying names as Python strings and we'll box them into the
    ``ctypes.c_char_p`` array PyOpenGL expects. Default buffer mode is
    ``GL_INTERLEAVED_ATTRIBS`` (the redbook9 demos that use TF —
    03-xfb, 10-draw-xfb — both call it ``GL_INTERLEAVED_ATTRIBS``)."""
    program: int = GL.glCreateProgram()
    shaders = list(shaders)
    for s in shaders:
        GL.glAttachShader(program, s)
    if tf_varyings is not None:
        encoded: list[bytes] = [
            v.encode("ascii") if isinstance(v, str) else v for v in tf_varyings
        ]
        _buffers = [ctypes.create_string_buffer(s) for s in encoded]
        lp_char = ctypes.POINTER(ctypes.c_char)
        ptrs = (lp_char * len(_buffers))(
            *[ctypes.cast(b, lp_char) for b in _buffers]
        )
        names_ptr = ctypes.cast(ptrs, ctypes.POINTER(lp_char))
        mode: GLenum = (
            tf_buffer_mode
            if tf_buffer_mode is not None
            else GL.GL_INTERLEAVED_ATTRIBS
        )
        GL.glTransformFeedbackVaryings(program, len(encoded), names_ptr, mode)
    GL.glLinkProgram(program)
    status: int = GL.glGetProgramiv(program, GL.GL_LINK_STATUS)
    if not status:
        log = GL.glGetProgramInfoLog(program).decode(errors="replace")
        GL.glDeleteProgram(program)
        raise ShaderError(f"program link failed: {log}")
    for s in shaders:
        GL.glDetachShader(program, s)
        if delete_shaders:
            GL.glDeleteShader(s)
    return program


def compile_program(
    *,
    vs: Optional[str] = None,
    fs: Optional[str] = None,
    gs: Optional[str] = None,
    tcs: Optional[str] = None,
    tes: Optional[str] = None,
    cs: Optional[str] = None,
    tf_varyings: Optional[Sequence[str]] = None,
    tf_buffer_mode: GLenum | None = None,
) -> int:
    """Compile a program from inline GLSL strings. Pass any subset of
    stages by keyword. Most demos use ``vs`` + ``fs``::

        program = common.compile_program(vs=VS_SOURCE, fs=FS_SOURCE)
    """
    pairs: list[tuple[str | None, GLenum]] = [
        (vs, GL.GL_VERTEX_SHADER),
        (fs, GL.GL_FRAGMENT_SHADER),
        (gs, GL.GL_GEOMETRY_SHADER),
        (tcs, GL.GL_TESS_CONTROL_SHADER),
        (tes, GL.GL_TESS_EVALUATION_SHADER),
        (cs, GL.GL_COMPUTE_SHADER),
    ]
    shaders: list[int] = [
        compile_shader(source=src, shader_type=kind)
        for src, kind in pairs
        if src is not None
    ]
    if not shaders:
        raise ShaderError("compile_program called with no stages")
    return link_program(
        shaders=shaders, tf_varyings=tf_varyings, tf_buffer_mode=tf_buffer_mode
    )


def compile_program_from_files(
    *,
    vs: Optional[str] = None,
    fs: Optional[str] = None,
    gs: Optional[str] = None,
    tcs: Optional[str] = None,
    tes: Optional[str] = None,
    cs: Optional[str] = None,
    tf_varyings: Optional[Sequence[str]] = None,
    tf_buffer_mode: GLenum | None = None,
) -> int:
    """Same as ``compile_program`` but each argument is a file path."""

    def _read(p: str | None) -> str | None:
        if p is None:
            return None
        # See compile_shader_from_file for why errors="replace".
        with open(p, mode="r", encoding="utf-8", errors="replace") as f:
            return f.read()

    return compile_program(
        vs=_read(vs),
        fs=_read(fs),
        gs=_read(gs),
        tcs=_read(tcs),
        tes=_read(tes),
        cs=_read(cs),
        tf_varyings=tf_varyings,
        tf_buffer_mode=tf_buffer_mode,
    )


# ---------------------------------------------------------------------------
# Texture loading (PIL fast path for DDS/TGA/PNG/BMP)
# ---------------------------------------------------------------------------
#
# The C++ side has ``vglLoadTexture`` (DDS only). The Red Book 9e media
# directory is mostly DDS, with one BMP and a couple of TGAs. PIL 9+
# can read all three, so we go through PIL and upload the result via
# ``glTexImage2D`` rather than reimplementing DXT decompression. If we
# ever hit a compressed format PIL can't decode, the right move is to
# add a ``glCompressedTexImage2D`` path that reads the raw blocks out
# of the DDS file directly.


def load_texture_2d(filename: str, *, generate_mipmaps: bool = True) -> int:
    """Load a PIL-readable image (the C++ ``lib/targa.cpp`` path) as an RGBA8
    2D texture and return its name.

    Rows are uploaded bottom-up: PIL decodes to top-left origin, and the
    flip puts the image in the row order the C++ TGA loader hands GL (a
    bottom-left-origin TGA is read raw there). DDS files take the
    ``dds.upload_2d`` path instead, which keeps the file's own row order
    and mip chain like ``vglLoadTexture``. Like both C++ loaders this sets
    no sampler state: the demo sets what its C++ sets.
    """
    from PIL import Image

    img = Image.open(filename).convert("RGBA")
    width, height = img.size
    # Pillow re-exports the Transpose enum members at module level at
    # runtime (verified: Pillow 11.3.0), but its stubs only declare
    # Image.Transpose.FLIP_TOP_BOTTOM.
    img = img.transpose(Image.FLIP_TOP_BOTTOM)  # ty: ignore[unresolved-attribute]
    data: bytes = img.tobytes()

    tex: int = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
    GL.glTexImage2D(
        GL.GL_TEXTURE_2D,
        0,
        GL.GL_RGBA8,
        width,
        height,
        0,
        GL.GL_RGBA,
        GL.GL_UNSIGNED_BYTE,
        data,
    )
    if generate_mipmaps:
        GL.glGenerateMipmap(GL.GL_TEXTURE_2D)
    return tex


def load_cubemap(face_filenames: Sequence[str]) -> int:
    """Load six PIL-readable images as a cubemap. ``face_filenames`` is
    a 6-tuple in the conventional GL order: +X, -X, +Y, -Y, +Z, -Z."""
    from PIL import Image

    targets: list[GLenum] = [
        GL.GL_TEXTURE_CUBE_MAP_POSITIVE_X,
        GL.GL_TEXTURE_CUBE_MAP_NEGATIVE_X,
        GL.GL_TEXTURE_CUBE_MAP_POSITIVE_Y,
        GL.GL_TEXTURE_CUBE_MAP_NEGATIVE_Y,
        GL.GL_TEXTURE_CUBE_MAP_POSITIVE_Z,
        GL.GL_TEXTURE_CUBE_MAP_NEGATIVE_Z,
    ]
    tex: int = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_CUBE_MAP, tex)
    for target, fname in zip(targets, face_filenames):
        img = Image.open(fname).convert("RGBA")
        # Cubemaps are notoriously orientation-sensitive; do NOT flip.
        # The C++ side uploads raw DDS face order without flipping.
        w, h = img.size
        GL.glTexImage2D(
            target,
            0,
            GL.GL_RGBA8,
            w,
            h,
            0,
            GL.GL_RGBA,
            GL.GL_UNSIGNED_BYTE,
            img.tobytes(),
        )
    GL.glTexParameteri(
        GL.GL_TEXTURE_CUBE_MAP, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR
    )
    GL.glTexParameteri(
        GL.GL_TEXTURE_CUBE_MAP, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR
    )
    GL.glTexParameteri(
        GL.GL_TEXTURE_CUBE_MAP, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE
    )
    GL.glTexParameteri(
        GL.GL_TEXTURE_CUBE_MAP, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE
    )
    GL.glTexParameteri(
        GL.GL_TEXTURE_CUBE_MAP, GL.GL_TEXTURE_WRAP_R, GL.GL_CLAMP_TO_EDGE
    )
    return tex

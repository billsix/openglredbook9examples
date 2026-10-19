"""Pure-Python loader for the .vbm mesh format used by Red Book 9e.

Mirrors ``lib/vbm.cpp``. The .vbm file is a small binary
header followed by interleaved attribute blocks (positions, normals,
texture coords are typical), followed optionally by index data and
material data.

This implementation:

  - reads the new-format header (magic ``'SBM1'`` = 0x314d4253) and
    falls back to the old-format header when the magic doesn't match,
    matching the C++ logic in ``LoadFromVBM``.
  - uploads the raw attribute blob into a single VBO (one
    ``glBufferData`` call), exactly as the C++ does.
  - sets up vertex attribute pointers with the same per-attribute
    component count and ``GL_FLOAT`` type, with stride 0 — i.e. each
    attribute is *contiguous* in the buffer, not interleaved per
    vertex. (vbm.cpp computes ``total_data_size`` per attribute and
    advances by that amount when computing the next attribute's
    offset; same here.)
  - allows the caller to remap attribute indices the way C++ does:
    ``LoadFromVBM(filename, vertexIndex, normalIndex, texCoord0Index)``.
    Pass ``-1`` to skip an attribute.

Usage::

    self.object = vbm.VBObject()
    self.object.load(common.media_path("armadillo_low.vbm"),
                     vertex_index=0, normal_index=1, tex0_index=2)
    self.object.bind_vao()
    self.object.render()                  # GL_TRIANGLES
    self.object.render(instances=200)     # instanced
"""

from __future__ import annotations

import ctypes
import io
import struct
from typing import List

import OpenGL.GL as GL
from OpenGL.constant import Constant

#: A value OpenGL accepts where it wants an enum -- PyOpenGL constants
#: resolve to `OpenGL.constant.Constant`, not `int`, so a plain `int`
#: annotation rejects them. Same house pattern as
#: src/modelviewprojection/wxapp.py.
type GLenum = int | Constant

_VBM_MAGIC_NEW: int = 0x314D4253  # 'SBM1'

# Header layouts. Each Python ``struct`` format omits the magic when
# already consumed; we read magic as a separate u32 to dispatch on it.
#
# vbm.h ``VBM_HEADER`` layout (8-byte aligned in C, but the file is
# packed tight — fields are u32 except ``name[64]``):
#
#   u32 magic
#   u32 size
#   char name[64]
#   u32 num_attribs
#   u32 num_frames
#   u32 num_vertices
#   u32 num_indices
#   u32 index_type
#   u32 num_materials
#   u32 flags
#
# Old (deprecated) header has an extra u32 ``num_chunks`` between
# ``num_frames`` and ``num_vertices``.

_NEW_HEADER_FMT: str = "<II64sIIIIIII"  # 4 + 4 + 64 + 4*7 = 100 bytes
_OLD_HEADER_FMT: str = "<II64sIIIIIIII"  # one more u32: 104 bytes

_ATTRIB_FMT: str = "<64sIII"  # name[64], type, components, flags  (76)
_FRAME_FMT: str = "<III"  # first, count, flags                 (12)


class VBObject:
    """Python equivalent of the C++ ``VBObject`` in vbm.h."""

    def __init__(self) -> None:
        self.vao = 0
        self.attr_buffer = 0
        self.index_buffer = 0
        self.num_vertices = 0
        self.num_indices = 0
        self.num_attribs = 0
        self.num_frames = 0
        self.num_materials = 0
        self.index_type: GLenum = GL.GL_UNSIGNED_INT
        self.frames: List[tuple] = []  # list of (first, count, flags)
        self.attribs: List[
            tuple
        ] = []  # list of (name, type, components, flags)

    # -- Loading --------------------------------------------------

    def load(
        self,
        filename: str,
        vertex_index: int = 0,
        normal_index: int = 1,
        tex0_index: int = 2,
    ) -> bool:
        """Read the .vbm file and upload its data to GPU. ``-1`` for
        any *_index argument skips that attribute. Returns True on
        success, False if the file could not be opened."""
        try:
            f: io.BufferedReader = open(filename, mode="rb")
        except FileNotFoundError:
            return False
        try:
            data: bytes = f.read()
        finally:
            f.close()

        # Read just the magic to choose a header layout.
        magic: int = struct.unpack_from("<I", data, offset=0)[0]

        if magic == _VBM_MAGIC_NEW:
            # The file's own ``size`` field is both the offset where the
            # attribute table starts and how many header bytes are real:
            # ``vbm.cpp`` zeroes its header struct and copies only
            # ``min(size, sizeof(VBM_HEADER))`` bytes. The shipped meshes
            # declare ``size = 92`` (no ``num_materials``/``flags``), so a
            # full-struct unpack would read those two fields from the start
            # of the attribute table.
            size: int = struct.unpack_from("<I", data, offset=4)[0]
            full_size: int = struct.calcsize(_NEW_HEADER_FMT)
            header_bytes: bytes = data[: min(size, full_size)].ljust(
                full_size, b"\x00"
            )
            (
                _magic,
                _size,
                _name,
                num_attribs,
                num_frames,
                num_vertices,
                num_indices,
                index_type,
                num_materials,
                flags,
            ) = struct.unpack_from(_NEW_HEADER_FMT, header_bytes, offset=0)
            header_size: int = size
        else:
            (
                _magic,
                size,
                _name,
                num_attribs,
                num_frames,
                _num_chunks,
                num_vertices,
                num_indices,
                index_type,
                num_materials,
                flags,
            ) = struct.unpack_from(_OLD_HEADER_FMT, data, offset=0)
            header_size = struct.calcsize(_OLD_HEADER_FMT)

        self.num_attribs = num_attribs
        self.num_frames = num_frames
        self.num_vertices = num_vertices
        self.num_indices = num_indices
        self.index_type = (
            GL.GL_UNSIGNED_SHORT
            if index_type == GL.GL_UNSIGNED_SHORT
            else GL.GL_UNSIGNED_INT
        )
        self.num_materials = num_materials

        # Attribute table starts at file offset ``header_size``.
        attr_table_off: int = header_size
        attr_size: int = struct.calcsize(_ATTRIB_FMT)
        self.attribs = []
        for i in range(num_attribs):
            name_b, atype, components, aflags = struct.unpack_from(
                _ATTRIB_FMT, data, offset=attr_table_off + i * attr_size
            )
            name: str = name_b.split(b"\x00", 1)[0].decode(
                "ascii", errors="replace"
            )
            self.attribs.append((name, atype, components, aflags))

        # Frame table follows attribute table.
        frame_table_off: int = attr_table_off + num_attribs * attr_size
        frame_size: int = struct.calcsize(_FRAME_FMT)
        self.frames = []
        for i in range(num_frames):
            first, count, fflags = struct.unpack_from(
                _FRAME_FMT, data, offset=frame_table_off + i * frame_size
            )
            self.frames.append((first, count, fflags))

        # Raw vertex data follows the frame table.
        raw_off: int = frame_table_off + num_frames * frame_size

        # Compute total attribute-blob size (each attribute is a flat
        # block of ``components * num_vertices * sizeof(GLfloat)`` —
        # the C++ assumes everything is float, even though the
        # attribute header carries a ``type`` field).
        total: int = 0
        for _n, _t, comps, _flg in self.attribs:
            total += comps * 4 * num_vertices
        attr_blob: bytes = data[raw_off : raw_off + total]

        # Index data follows the attribute blob.
        if num_indices:
            element_size: int = (
                2 if self.index_type == GL.GL_UNSIGNED_SHORT else 4
            )
            idx_off: int = raw_off + total
            idx_blob: bytes | None = data[
                idx_off : idx_off + num_indices * element_size
            ]
        else:
            idx_blob = None

        # GL upload --------------------------------------------------
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)

        self.attr_buffer = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.attr_buffer)
        GL.glBufferData(
            target=GL.GL_ARRAY_BUFFER,
            size=len(attr_blob),
            data=attr_blob,
            usage=GL.GL_STATIC_DRAW,
        )

        # Set up attribute pointers. Attribute index remap matches the
        # C++: index 0 → vertex_index, 1 → normal_index, 2 → tex0_index;
        # any further attributes are passed through with their original
        # index. ``-1`` means skip.
        offset: int = 0
        for i, (_name, atype, comps, _flags) in enumerate(self.attribs):
            if i == 0:
                ai: int = vertex_index
            elif i == 1:
                ai = normal_index
            elif i == 2:
                ai = tex0_index
            else:
                ai = i

            stride: int = 0  # contiguous within the attribute block
            if ai >= 0:
                GL.glVertexAttribPointer(
                    index=ai,
                    size=comps,
                    type=atype,
                    normalized=GL.GL_FALSE,
                    stride=stride,
                    pointer=ctypes.c_void_p(offset),
                )
                GL.glEnableVertexAttribArray(ai)
            offset += comps * 4 * num_vertices

        if idx_blob is not None:
            self.index_buffer = GL.glGenBuffers(1)
            GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.index_buffer)
            GL.glBufferData(
                target=GL.GL_ELEMENT_ARRAY_BUFFER,
                size=len(idx_blob),
                data=idx_blob,
                usage=GL.GL_STATIC_DRAW,
            )

        return True

    # -- Drawing --------------------------------------------------

    def bind_vao(self) -> None:
        GL.glBindVertexArray(self.vao)

    def render(self, frame_index: int = 0, instances: int = 0) -> None:
        """Draw the model. ``instances=0`` is non-instanced (matches
        the C++ default arg). The C++ renders ``GL_TRIANGLES``."""
        if frame_index >= self.num_frames:
            return
        first, count, _flags = self.frames[frame_index]

        GL.glBindVertexArray(self.vao)
        if instances:
            if self.num_indices:
                element_size: int = (
                    2 if self.index_type == GL.GL_UNSIGNED_SHORT else 4
                )
                GL.glDrawElementsInstanced(
                    GL.GL_TRIANGLES,
                    count,
                    self.index_type,
                    ctypes.c_void_p(first * element_size),
                    instances,
                )
            else:
                GL.glDrawArraysInstanced(
                    GL.GL_TRIANGLES, first, count, instances
                )
        else:
            if self.num_indices:
                element_size: int = (
                    2 if self.index_type == GL.GL_UNSIGNED_SHORT else 4
                )
                GL.glDrawElements(
                    GL.GL_TRIANGLES,
                    count,
                    self.index_type,
                    ctypes.c_void_p(first * element_size),
                )
            else:
                GL.glDrawArrays(GL.GL_TRIANGLES, first, count)

    # -- Cleanup --------------------------------------------------

    def free(self) -> None:
        if self.attr_buffer:
            GL.glDeleteBuffers(1, [self.attr_buffer])
        if self.index_buffer:
            GL.glDeleteBuffers(1, [self.index_buffer])
        if self.vao:
            GL.glDeleteVertexArrays(1, [self.vao])
        self.attr_buffer = self.index_buffer = self.vao = 0

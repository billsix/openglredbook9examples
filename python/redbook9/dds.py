"""Minimal DDS reader for the demos that need cube maps or volume DDS.

PIL handles 2D DDS fine, but cube maps and volumes are returned as a
single image. Several Red Book 9e demos need explicit access to all 6
cube faces or to a volume's slices, so this module reads the DDS
header + raw pixel data ourselves and uploads via OpenGL directly.

Supports the formats the v9 media uses:
  - Uncompressed RGBA8 / BGRA8
  - DXT1 / DXT3 / DXT5 (BC1 / BC2 / BC3) — uploaded as compressed
    via ``glCompressedTexImage2D`` so the GPU does decompression.

References: https://learn.microsoft.com/en-us/windows/win32/direct3ddds/dx-graphics-dds-pguide
"""

from __future__ import annotations

import dataclasses
import struct

import OpenGL.GL as GL
from OpenGL.constant import Constant

#: A value OpenGL accepts where it wants an enum -- PyOpenGL constants
#: resolve to `OpenGL.constant.Constant`, not `int`, so a plain `int`
#: annotation rejects them. Same house pattern as
#: src/modelviewprojection/wxapp.py.
type GLenum = int | Constant

DDS_MAGIC: int = 0x20534444  # 'DDS '

# dwFlags
DDSD_CAPS: int = 0x1
DDSD_HEIGHT: int = 0x2
DDSD_WIDTH: int = 0x4
DDSD_PITCH: int = 0x8
DDSD_PIXELFORMAT: int = 0x1000
DDSD_MIPMAPCOUNT: int = 0x20000
DDSD_LINEARSIZE: int = 0x80000
DDSD_DEPTH: int = 0x800000

# dwCaps2 cubemap flags
DDSCAPS2_CUBEMAP: int = 0x200
DDSCAPS2_CUBEMAP_POSITIVEX: int = 0x400
DDSCAPS2_CUBEMAP_NEGATIVEX: int = 0x800
DDSCAPS2_CUBEMAP_POSITIVEY: int = 0x1000
DDSCAPS2_CUBEMAP_NEGATIVEY: int = 0x2000
DDSCAPS2_CUBEMAP_POSITIVEZ: int = 0x4000
DDSCAPS2_CUBEMAP_NEGATIVEZ: int = 0x8000
DDSCAPS2_VOLUME: int = 0x200000

# Pixel format flags
DDPF_FOURCC: int = 0x4
DDPF_RGB: int = 0x40
DDPF_ALPHAPIXELS: int = 0x1


def _fourcc(s: str) -> int:
    return struct.unpack("<I", s.encode("ascii"))[0]


_FCC_DXT1: int = _fourcc("DXT1")
_FCC_DXT3: int = _fourcc("DXT3")
_FCC_DXT5: int = _fourcc("DXT5")
_FCC_DX10: int = _fourcc("DX10")


# Numeric ``dwFourCC`` values used by some old D3D9 tools — they pack a
# small integer (a ``D3DFORMAT`` enum value) into the FourCC field
# instead of a 4-character code. Used for HDR float textures that
# predate the DX10 header. Only listing the ones the redbook9 media
# uses.
_D3DFMT: dict[int, tuple[str, str, int]] = {
    111: ("uncompressed", "R16F", 16),  # bits per pixel
    112: ("uncompressed", "RG16F", 32),
    113: ("uncompressed", "RGBA16F", 64),
    114: ("uncompressed", "R32F", 32),
    115: ("uncompressed", "RG32F", 64),
    116: ("uncompressed", "RGBA32F", 128),
}


# Subset of DXGI_FORMAT enum values used by DX10-extended DDS files in
# the redbook9 media tree. Each value maps to (kind, internal_format,
# pixel_format, pixel_type, bpp_or_block_size).
_DXGI_FORMAT_R32G32B32A32_FLOAT: int = 2
_DXGI_FORMAT_R16G16B16A16_FLOAT: int = 10
_DXGI_FORMAT_R8G8B8A8_UNORM: int = 28
_DXGI_FORMAT_R8_UNORM: int = 61
_DXGI_FORMAT_BC1_UNORM: int = 71
_DXGI_FORMAT_BC2_UNORM: int = 74
_DXGI_FORMAT_BC3_UNORM: int = 77


@dataclasses.dataclass(slots=True, kw_only=True)
class DDS:
    """Parsed DDS file. ``faces[i]`` is a list of mip-level bytes
    objects for cube face ``i`` (one face for 2D / volume textures)."""

    width: int
    height: int
    depth: int
    mips: int
    format_kind: str  # "compressed" | "rgba"
    fourcc: int
    faces: list[list[bytes]]
    internal_format: GLenum
    pixel_format: GLenum | None
    pixel_type: GLenum | None
    block_size: int  # bytes per 4×4 block, when compressed


def _level_byte_size(
    width: int, height: int, format_kind: str, block_size: int, bpp: int
) -> int:
    if format_kind == "compressed":
        bw: int = max(1, (width + 3) // 4)
        bh: int = max(1, (height + 3) // 4)
        return bw * bh * block_size
    return width * height * bpp // 8


def load(path: str) -> DDS:
    with open(path, mode="rb") as f:
        data: bytes = f.read()

    if struct.unpack_from("<I", data, offset=0)[0] != DDS_MAGIC:
        raise ValueError(f"not a DDS file: {path!r}")

    # DDS_HEADER (124 bytes after the magic). Layout from the
    # microsoft DDS spec:
    #   offset 0:   magic 'DDS ' (4)
    #   offset 4:   dwSize          (DDS_HEADER starts here, total 124 bytes)
    #   offset 8:   dwFlags
    #   offset 12:  dwHeight
    #   offset 16:  dwWidth
    #   offset 20:  dwPitchOrLinearSize
    #   offset 24:  dwDepth
    #   offset 28:  dwMipMapCount
    #   offset 32:  dwReserved1[11]    (44 bytes)
    #   offset 76:  DDS_PIXELFORMAT    (32 bytes)
    #   offset 108: dwCaps
    #   offset 112: dwCaps2
    #   offset 116: dwCaps3
    #   offset 120: dwCaps4
    #   offset 124: dwReserved2
    # If pf.fourcc == 'DX10' there's an additional DDS_HEADER_DXT10
    # (20 bytes) at offset 128 before the pixel data.
    (size, flags, height, width, _pitch, depth, mip_count) = struct.unpack_from(
        "<IIIIIII", data, offset=4
    )

    pf_off: int = (
        4 + 7 * 4 + 11 * 4
    )  # = 76 (4 magic + 28 prelude + 44 reserved)
    (
        pf_size,
        pf_flags,
        pf_fourcc,
        pf_bits,
        pf_rmask,
        pf_gmask,
        pf_bmask,
        pf_amask,
    ) = struct.unpack_from("<IIIIIIII", data, offset=pf_off)

    caps_off: int = pf_off + 32
    (caps1, caps2, _caps3, _caps4) = struct.unpack_from(
        "<IIII", data, offset=caps_off
    )

    is_cubemap: bool = bool(caps2 & DDSCAPS2_CUBEMAP)
    is_volume: bool = bool(caps2 & DDSCAPS2_VOLUME)
    mips: int = max(1, mip_count) if (flags & DDSD_MIPMAPCOUNT) else 1

    # Pixel data starts right after the standard 124-byte header
    # (offset 128) — *unless* the file uses the DX10 extended header,
    # in which case skip another 20 bytes for that.
    cursor: int = 128
    dx10_dxgi: int | None = None
    if (pf_flags & DDPF_FOURCC) and pf_fourcc == _FCC_DX10:
        # DDS_HEADER_DXT10: dxgiFormat, resourceDimension, miscFlag,
        # arraySize, miscFlags2 (5 u32 = 20 bytes).
        (dx10_dxgi, _res_dim, _misc, _array_size, _misc2) = struct.unpack_from(
            "<IIIII", data, offset=128
        )
        cursor = 148

    # Pick the GL format based on (in priority order):
    #   1. DX10 extended header dxgiFormat, if present.
    #   2. DXTn 4-character FourCC.
    #   3. Numeric D3DFMT_* in the FourCC field.
    #   4. RGB / RGBA bit-mask path.
    if dx10_dxgi is not None:
        if dx10_dxgi == _DXGI_FORMAT_R8_UNORM:
            format_kind: str = "rgba"
            internal_format: GLenum = GL.GL_R8
            pixel_format: GLenum | None = GL.GL_RED
            pixel_type: GLenum | None = GL.GL_UNSIGNED_BYTE
            bpp: int = 8
            block_size: int = 0
        elif dx10_dxgi == _DXGI_FORMAT_R8G8B8A8_UNORM:
            format_kind = "rgba"
            internal_format = GL.GL_RGBA8
            pixel_format = GL.GL_RGBA
            pixel_type = GL.GL_UNSIGNED_BYTE
            bpp = 32
            block_size = 0
        elif dx10_dxgi == _DXGI_FORMAT_R16G16B16A16_FLOAT:
            format_kind = "rgba"
            internal_format = GL.GL_RGBA16F
            pixel_format = GL.GL_RGBA
            pixel_type = GL.GL_HALF_FLOAT
            bpp = 64
            block_size = 0
        elif dx10_dxgi == _DXGI_FORMAT_R32G32B32A32_FLOAT:
            format_kind = "rgba"
            internal_format = GL.GL_RGBA32F
            pixel_format = GL.GL_RGBA
            pixel_type = GL.GL_FLOAT
            bpp = 128
            block_size = 0
        elif dx10_dxgi == _DXGI_FORMAT_BC1_UNORM:
            format_kind = "compressed"
            internal_format = 0x83F1
            pixel_format = pixel_type = None
            bpp = 0
            block_size = 8
        elif dx10_dxgi == _DXGI_FORMAT_BC2_UNORM:
            format_kind = "compressed"
            internal_format = 0x83F2
            pixel_format = pixel_type = None
            bpp = 0
            block_size = 16
        elif dx10_dxgi == _DXGI_FORMAT_BC3_UNORM:
            format_kind = "compressed"
            internal_format = 0x83F3
            pixel_format = pixel_type = None
            bpp = 0
            block_size = 16
        else:
            raise NotImplementedError(
                f"DDS DXGI_FORMAT {dx10_dxgi} not supported in {path!r}"
            )
    elif pf_flags & DDPF_FOURCC:
        if pf_fourcc == _FCC_DXT1:
            internal_format = 0x83F1  # GL_COMPRESSED_RGBA_S3TC_DXT1_EXT
            block_size = 8
            format_kind = "compressed"
            pixel_format = pixel_type = None
            bpp = 0
        elif pf_fourcc == _FCC_DXT3:
            internal_format = 0x83F2
            block_size = 16
            format_kind = "compressed"
            pixel_format = pixel_type = None
            bpp = 0
        elif pf_fourcc == _FCC_DXT5:
            internal_format = 0x83F3
            block_size = 16
            format_kind = "compressed"
            pixel_format = pixel_type = None
            bpp = 0
        elif pf_fourcc in _D3DFMT:
            # Numeric FourCC = legacy D3DFMT_* enum value, used for
            # HDR float formats that predate the DX10 header.
            _, name, fmt_bpp = _D3DFMT[pf_fourcc]
            format_kind = "rgba"
            block_size = 0
            bpp = fmt_bpp
            if name == "R16F":
                internal_format, pixel_format, pixel_type = (
                    GL.GL_R16F,
                    GL.GL_RED,
                    GL.GL_HALF_FLOAT,
                )
            elif name == "RG16F":
                internal_format, pixel_format, pixel_type = (
                    GL.GL_RG16F,
                    GL.GL_RG,
                    GL.GL_HALF_FLOAT,
                )
            elif name == "RGBA16F":
                internal_format, pixel_format, pixel_type = (
                    GL.GL_RGBA16F,
                    GL.GL_RGBA,
                    GL.GL_HALF_FLOAT,
                )
            elif name == "R32F":
                internal_format, pixel_format, pixel_type = (
                    GL.GL_R32F,
                    GL.GL_RED,
                    GL.GL_FLOAT,
                )
            elif name == "RG32F":
                internal_format, pixel_format, pixel_type = (
                    GL.GL_RG32F,
                    GL.GL_RG,
                    GL.GL_FLOAT,
                )
            elif name == "RGBA32F":
                internal_format, pixel_format, pixel_type = (
                    GL.GL_RGBA32F,
                    GL.GL_RGBA,
                    GL.GL_FLOAT,
                )
            else:
                raise NotImplementedError(
                    f"D3DFMT {pf_fourcc} mapping incomplete"
                )
        else:
            raise NotImplementedError(
                f"DDS FourCC 0x{pf_fourcc:08X} not supported in {path!r}"
            )
    elif pf_flags & DDPF_RGB:
        # Treat as BGRA8 / BGRX8 (most common).
        bpp = pf_bits
        format_kind = "rgba"
        block_size = 0
        if bpp == 32:
            internal_format = GL.GL_RGBA8
            pixel_format = GL.GL_BGRA
            pixel_type = GL.GL_UNSIGNED_BYTE
        else:
            internal_format = GL.GL_RGB8
            pixel_format = GL.GL_BGR
            pixel_type = GL.GL_UNSIGNED_BYTE
    else:
        raise NotImplementedError(
            f"DDS pixel format flags 0x{pf_flags:08X} not supported in {path!r}"
        )

    num_faces: int = 6 if is_cubemap else 1
    faces: list[list[bytes]] = []
    for _f in range(num_faces):
        levels: list[bytes] = []
        w, h, d = width, height, max(1, depth) if is_volume else 1
        for _m in range(mips):
            sz: int = _level_byte_size(
                width=w,
                height=h,
                format_kind=format_kind,
                block_size=block_size,
                bpp=bpp,
            )
            if is_volume:
                sz *= d
            levels.append(bytes(data[cursor : cursor + sz]))
            cursor += sz
            w: int = max(1, w // 2)
            h: int = max(1, h // 2)
            d: int = max(1, d // 2)
        faces.append(levels)

    return DDS(
        width=width,
        height=height,
        depth=max(1, depth),
        mips=mips,
        format_kind=format_kind,
        fourcc=pf_fourcc,
        faces=faces,
        internal_format=internal_format,
        pixel_format=pixel_format,
        pixel_type=pixel_type,
        block_size=block_size,
    )


def upload_2d(path: str) -> int:
    """Load a 2D DDS as ``GL_TEXTURE_2D`` and return the texture
    name. Includes any mip levels stored in the file."""
    dds: DDS = load(path)
    tex: int = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
    w, h = dds.width, dds.height
    for level, blob in enumerate(dds.faces[0]):
        if dds.format_kind == "compressed":
            GL.glCompressedTexImage2D(
                GL.GL_TEXTURE_2D,
                level,
                dds.internal_format,
                w,
                h,
                0,
                len(blob),
                blob,
            )
        else:
            GL.glTexImage2D(
                GL.GL_TEXTURE_2D,
                level,
                dds.internal_format,
                w,
                h,
                0,
                dds.pixel_format,
                dds.pixel_type,
                blob,
            )
        w: int = max(1, w // 2)
        h: int = max(1, h // 2)
    # No sampler state: like the C++ ``vglLoadTexture`` the uploader leaves
    # the GL defaults (``GL_NEAREST_MIPMAP_LINEAR`` / ``GL_REPEAT``) and each
    # demo sets exactly the parameters its C++ sets.
    return tex


def upload_cubemap(path: str) -> int:
    """Load a cubemap DDS as ``GL_TEXTURE_CUBE_MAP``. Faces are read
    in DDS order (POSITIVEX, NEGATIVEX, POSITIVEY, NEGATIVEY,
    POSITIVEZ, NEGATIVEZ)."""
    dds: DDS = load(path)
    if len(dds.faces) != 6:
        raise ValueError(f"{path!r} is not a cubemap DDS")
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
    for tgt, levels in zip(targets, dds.faces):
        w, h = dds.width, dds.height
        for level, blob in enumerate(levels):
            if dds.format_kind == "compressed":
                GL.glCompressedTexImage2D(
                    tgt, level, dds.internal_format, w, h, 0, len(blob), blob
                )
            else:
                GL.glTexImage2D(
                    tgt,
                    level,
                    dds.internal_format,
                    w,
                    h,
                    0,
                    dds.pixel_format,
                    dds.pixel_type,
                    blob,
                )
            w: int = max(1, w // 2)
            h: int = max(1, h // 2)
    # No sampler state, as ``vglLoadTexture`` (see ``upload_2d``); the C++
    # cubemap demo relies on the GL defaults plus GL_TEXTURE_CUBE_MAP_SEAMLESS.
    return tex


def upload_3d(path: str) -> int:
    """Load a volume DDS as ``GL_TEXTURE_3D``."""
    dds: DDS = load(path)
    tex: int = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_3D, tex)
    w, h, d = dds.width, dds.height, dds.depth
    for level, blob in enumerate(dds.faces[0]):
        if dds.format_kind == "compressed":
            GL.glCompressedTexImage3D(
                GL.GL_TEXTURE_3D,
                level,
                dds.internal_format,
                w,
                h,
                d,
                0,
                len(blob),
                blob,
            )
        else:
            GL.glTexImage3D(
                GL.GL_TEXTURE_3D,
                level,
                dds.internal_format,
                w,
                h,
                d,
                0,
                dds.pixel_format,
                dds.pixel_type,
                blob,
            )
        w: int = max(1, w // 2)
        h: int = max(1, h // 2)
        d: int = max(1, d // 2)
    # No sampler state, as ``vglLoadTexture`` (see ``upload_2d``). In
    # particular the wrap mode stays at the GL default GL_REPEAT: the volume
    # demo rotates its texture coordinates out of [0,1]^3 and the C++ tiles
    # the cloud there; a clamp would smear the edge voxels instead.
    return tex

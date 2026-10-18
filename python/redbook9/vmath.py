"""Subset of ``vmath.h`` (Red Book 9e) ported to numpy.

Same API as the v7 port's ``vmath.py`` so the two ports look alike.
Convention: matrices stored as ``numpy.float32`` of shape ``(4, 4)``,
indexed mathematically by ``mat[row, col]``. Multiplication is ``@``.
When uploading to a GLSL ``mat4`` use ``upload(loc, mat)`` — it passes
``transpose=GL_TRUE`` to convert row-major numpy into the column-major
layout GLSL expects.

The C++ ``vmath`` library uses degrees for ``rotate`` and right-handed
projections (``perspective``, ``frustum``). Same here.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import OpenGL.GL as GL


def vec3(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> np.ndarray:
    return np.array([x, y, z], dtype=np.float32)


def vec4(
    x: float = 0.0, y: float = 0.0, z: float = 0.0, w: float = 1.0
) -> np.ndarray:
    return np.array([x, y, z, w], dtype=np.float32)


def identity() -> np.ndarray:
    return np.identity(4, dtype=np.float32)


def translate(
    x: float | Sequence[float] | np.ndarray,
    y: float | None = None,
    z: float | None = None,
) -> np.ndarray:
    if y is None and z is None:
        # The one-argument overload's contract: x is a 3-sequence when
        # y and z are omitted. ty cannot narrow the scalar members of
        # the union out of x from the y/z check.
        x, y, z = float(x[0]), float(x[1]), float(x[2])  # ty: ignore[not-subscriptable]
    m = identity()
    m[0, 3] = x
    m[1, 3] = y
    m[2, 3] = z
    return m


def scale(
    x: float | Sequence[float] | np.ndarray,
    y: float | None = None,
    z: float | None = None,
) -> np.ndarray:
    if y is None and z is None:
        if hasattr(x, "__len__"):
            # Anything sized we accept here (list/tuple/ndarray) is
            # also subscriptable; hasattr narrows ty only to a
            # __len__-bearing protocol, which it can't subscript.
            x, y, z = float(x[0]), float(x[1]), float(x[2])  # ty: ignore[not-subscriptable]
        else:
            x = y = z = float(x)
    m = identity()
    m[0, 0] = x
    m[1, 1] = y
    m[2, 2] = z
    return m


def rotate(
    angle_degrees: float,
    ax: float,
    ay: float | None = None,
    az: float | None = None,
) -> np.ndarray:
    """Two overloads mirror the C++ ``vmath::rotate``:

      * ``rotate(angle, x, y, z)``   — rotate around (x,y,z) axis
      * ``rotate(angle_x, angle_y, angle_z)`` — Z-Y-X Euler triple

    Disambiguated by argument count, like the C++ overload set.
    """
    if ay is None and az is None:
        # Single arg: just rotate around Z (rare; included for parity)
        return _rotate_axis(angle_degrees=angle_degrees, ax=0.0, ay=0.0, az=1.0)
    if az is None:
        # Two args isn't a vmath overload — fall through to error
        raise TypeError("rotate() takes either (angle,x,y,z) or (rx,ry,rz)")
    # The overload contract pairs ay with az: the 4-arg axis form
    # passes both. ty only rules out the both-None and az-None cases
    # above, so it still sees `ay: float | None` here.
    return _rotate_axis(angle_degrees=angle_degrees, ax=ax, ay=ay, az=az)  # ty: ignore[invalid-argument-type]


def rotate_xyz(rx: float, ry: float, rz: float) -> np.ndarray:
    """Z-Y-X Euler convention. Angles in degrees. This is what
    ``vmath::rotate(x, y, z)`` (the 3-arg overload) computes."""
    return (
        _rotate_axis(angle_degrees=rz, ax=0, ay=0, az=1)
        @ _rotate_axis(angle_degrees=ry, ax=0, ay=1, az=0)
        @ _rotate_axis(angle_degrees=rx, ax=1, ay=0, az=0)
    )


def _rotate_axis(
    angle_degrees: float, ax: float, ay: float, az: float
) -> np.ndarray:
    n: float = math.sqrt(ax * ax + ay * ay + az * az)
    if n == 0.0:
        return identity()
    ax, ay, az = ax / n, ay / n, az / n
    a: float = math.radians(angle_degrees)
    c: float = math.cos(a)
    s = math.sin(a)
    omc = 1.0 - c
    m = identity()
    m[0, 0] = c + ax * ax * omc
    m[0, 1] = ax * ay * omc - az * s
    m[0, 2] = ax * az * omc + ay * s
    m[1, 0] = ay * ax * omc + az * s
    m[1, 1] = c + ay * ay * omc
    m[1, 2] = ay * az * omc - ax * s
    m[2, 0] = az * ax * omc - ay * s
    m[2, 1] = az * ay * omc + ax * s
    m[2, 2] = c + az * az * omc
    return m


def perspective(
    fovy_degrees: float, aspect: float, near: float, far: float
) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fovy_degrees) * 0.5)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2.0 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


def perspective_mat_h(
    fovy_degrees: float, aspect: float, near: float, far: float
) -> np.ndarray:
    """``Perspective`` as Angel's ``include/mat.h`` computes it.

    ``mat.h``'s ``Perspective`` (and ``Frustum``) fill a ``mat4 c`` whose
    default constructor is the identity and never clear ``c[3][3]``, so the
    clip-space ``w`` comes out as ``1 - z_eye`` instead of ``-z_eye``: the
    picture is pushed back by one unit of depth and foreshortens less than
    the textbook matrix. The two demos that include ``mat.h`` (09-simpletess,
    09-teapot) draw that picture, so they use this; every other demo's
    ``vmath.h`` is matched by ``perspective``.
    """
    m: np.ndarray = perspective(
        fovy_degrees=fovy_degrees, aspect=aspect, near=near, far=far
    )
    m[3, 3] = 1.0
    return m


def frustum(
    left: float,
    right: float,
    bottom: float,
    top: float,
    near: float,
    far: float,
) -> np.ndarray:
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = (2.0 * near) / (right - left)
    m[0, 2] = (right + left) / (right - left)
    m[1, 1] = (2.0 * near) / (top - bottom)
    m[1, 2] = (top + bottom) / (top - bottom)
    m[2, 2] = -(far + near) / (far - near)
    m[2, 3] = -(2.0 * far * near) / (far - near)
    m[3, 2] = -1.0
    return m


def ortho(
    left: float,
    right: float,
    bottom: float,
    top: float,
    near: float,
    far: float,
) -> np.ndarray:
    m = identity()
    m[0, 0] = 2.0 / (right - left)
    m[1, 1] = 2.0 / (top - bottom)
    m[2, 2] = -2.0 / (far - near)
    m[0, 3] = -(right + left) / (right - left)
    m[1, 3] = -(top + bottom) / (top - bottom)
    m[2, 3] = -(far + near) / (far - near)
    return m


def lookat(
    eye: Sequence[float] | np.ndarray,
    center: Sequence[float] | np.ndarray,
    up: Sequence[float] | np.ndarray,
) -> np.ndarray:
    eye: np.ndarray = np.asarray(eye, dtype=np.float32)
    center: np.ndarray = np.asarray(center, dtype=np.float32)
    up: np.ndarray = np.asarray(up, dtype=np.float32)

    f = center - eye
    f /= np.linalg.norm(f)
    upn = up / np.linalg.norm(up)
    # ``vmath::lookat`` does NOT normalise ``s`` (nor ``u``): when the view
    # direction is not perpendicular to ``up``, the C++ matrix scales eye x/y
    # by ``sin(angle(f, up))``. That is the picture the demos draw
    # (04-shadowmap's lit footprint on the ground depends on it), so the
    # port reproduces it rather than the textbook orthonormal basis.
    s = np.cross(f, upn)
    u = np.cross(s, f)

    m = identity()
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -np.dot(s, eye)
    m[1, 3] = -np.dot(u, eye)
    m[2, 3] = np.dot(f, eye)
    return m


def upload(location: int, mat: np.ndarray) -> None:
    """Upload a row-major numpy mat4 to a GLSL ``mat4`` uniform.
    GL_TRUE transposes our row-major storage into GLSL's column-major
    expectation."""
    GL.glUniformMatrix4fv(
        location, 1, GL.GL_TRUE, np.ascontiguousarray(mat, dtype=np.float32)
    )


def upload_array(
    location: int, mats: Sequence[np.ndarray] | np.ndarray
) -> None:
    """Upload an array of mat4 (e.g. ``mat4[N]`` uniform). Accepts a
    list of (4,4) arrays or a single (N,4,4) array."""
    arr = np.ascontiguousarray(np.stack(list(mats), axis=0), dtype=np.float32)
    GL.glUniformMatrix4fv(location, arr.shape[0], GL.GL_TRUE, arr)

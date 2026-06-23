"""
section_props.py
----------------
Calculates geometric properties of 2D cross-sections composed of one or more
closed polygons (with possible holes), using Green's formulas (contour integrals).

Axis convention (section-local):
    Y = horizontal (transverse), Z = vertical.
    Longitudinal axis X is perpendicular to the section plane.

Output per section:
    A         - total area [units^2]
    yc, zc    - centroid of the composite section
    Iyy, Izz  - second moments about centroidal axes (Iyy = integral(z^2 dA))
    Iyz       - product of inertia about centroid
    I1, I2    - principal moments (major and minor)
    theta_pp  - angle of major principal axis from Y, in degrees
    y_max, y_min, z_max, z_min - extreme coordinates relative to centroid
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union


def _ring_properties(coords: np.ndarray) -> tuple[float, float, float, float, float, float]:
    """
    Properties of a closed ring given as array (N, 2) of (y, z).
    Returns (A, Sy, Sz, Iyy_o, Izz_o, Iyz_o) in global axes (origin).
    """
    y = coords[:, 0]
    z = coords[:, 1]
    y1 = np.roll(y, -1)
    z1 = np.roll(z, -1)

    cross = y * z1 - y1 * z
    A = 0.5 * cross.sum()

    Sz = (1 / 6) * ((y + y1) * cross).sum()
    Sy = (1 / 6) * ((z + z1) * cross).sum()

    Iyy_o = (1 / 12) * ((z**2 + z * z1 + z1**2) * cross).sum()
    Izz_o = (1 / 12) * ((y**2 + y * y1 + y1**2) * cross).sum()
    Iyz_o = (1 / 24) * ((2 * y * z + y * z1 + y1 * z + 2 * y1 * z1) * cross).sum()

    return A, Sy, Sz, Iyy_o, Izz_o, Iyz_o


@dataclass
class SectionProperties:
    A: float
    yc: float
    zc: float
    Iyy: float
    Izz: float
    Iyz: float
    I1: float
    I2: float
    theta_pp_deg: float
    y_max: float
    y_min: float
    z_max: float
    z_min: float

    def as_dict(self) -> dict:
        return {
            "A": self.A,
            "yc": self.yc,
            "zc": self.zc,
            "Iyy": self.Iyy,
            "Izz": self.Izz,
            "Iyz": self.Iyz,
            "I1": self.I1,
            "I2": self.I2,
            "theta_pp_deg": self.theta_pp_deg,
            "y_max": self.y_max,
            "y_min": self.y_min,
            "z_max": self.z_max,
            "z_min": self.z_min,
        }


def _principal_axes(Iyy: float, Izz: float, Iyz: float) -> tuple[float, float, float]:
    """Diagonalize the 2x2 inertia tensor. Returns (I1, I2, theta_deg)."""
    avg = 0.5 * (Iyy + Izz)
    diff = 0.5 * (Iyy - Izz)
    R = np.hypot(diff, Iyz)
    I1 = avg + R
    I2 = avg - R
    theta = 0.5 * np.arctan2(-2.0 * Iyz, Izz - Iyy)
    return I1, I2, np.degrees(theta)


def properties_from_polygons(polygons: list[Polygon]) -> SectionProperties:
    """
    Calculate properties of a section composed of Shapely polygons.
    Polygons may be disjoint or overlapping; they are unioned first.
    """
    if not polygons:
        raise ValueError("Empty polygon list.")

    merged = unary_union(polygons)
    if isinstance(merged, Polygon):
        geoms = [merged]
    elif isinstance(merged, MultiPolygon):
        geoms = list(merged.geoms)
    else:
        raise ValueError(f"Unioned geometry is not a polygon: {type(merged)}")

    A_tot = 0.0
    Sy_tot = 0.0
    Sz_tot = 0.0
    Iyy_o = 0.0
    Izz_o = 0.0
    Iyz_o = 0.0

    for poly in geoms:
        ext = np.array(poly.exterior.coords)
        if not np.allclose(ext[0], ext[-1]):
            ext = np.vstack([ext, ext[0]])
        if Polygon(ext).exterior.is_ccw is False:
            ext = ext[::-1]
        A_e, Sy_e, Sz_e, Iyy_e, Izz_e, Iyz_e = _ring_properties(ext[:-1])

        A_tot += A_e
        Sy_tot += Sy_e
        Sz_tot += Sz_e
        Iyy_o += Iyy_e
        Izz_o += Izz_e
        Iyz_o += Iyz_e

        for interior in poly.interiors:
            ring = np.array(interior.coords)
            if not np.allclose(ring[0], ring[-1]):
                ring = np.vstack([ring, ring[0]])
            if Polygon(ring).exterior.is_ccw is True:
                ring = ring[::-1]
            A_h, Sy_h, Sz_h, Iyy_h, Izz_h, Iyz_h = _ring_properties(ring[:-1])
            A_tot += A_h
            Sy_tot += Sy_h
            Sz_tot += Sz_h
            Iyy_o += Iyy_h
            Izz_o += Izz_h
            Iyz_o += Iyz_h

    if abs(A_tot) < 1e-12:
        raise ValueError("Null total area.")

    yc = Sz_tot / A_tot
    zc = Sy_tot / A_tot

    Iyy_c = Iyy_o - A_tot * zc**2
    Izz_c = Izz_o - A_tot * yc**2
    Iyz_c = Iyz_o - A_tot * yc * zc

    I1, I2, theta = _principal_axes(Iyy_c, Izz_c, Iyz_c)

    all_y = []
    all_z = []
    for poly in geoms:
        coords = np.array(poly.exterior.coords)
        all_y.extend(coords[:, 0].tolist())
        all_z.extend(coords[:, 1].tolist())
        for interior in poly.interiors:
            coords = np.array(interior.coords)
            all_y.extend(coords[:, 0].tolist())
            all_z.extend(coords[:, 1].tolist())

    y_max = max(all_y) - yc
    y_min = min(all_y) - yc
    z_max = max(all_z) - zc
    z_min = min(all_z) - zc

    return SectionProperties(
        A=A_tot,
        yc=yc,
        zc=zc,
        Iyy=Iyy_c,
        Izz=Izz_c,
        Iyz=Iyz_c,
        I1=I1,
        I2=I2,
        theta_pp_deg=theta,
        y_max=y_max,
        y_min=y_min,
        z_max=z_max,
        z_min=z_min,
    )

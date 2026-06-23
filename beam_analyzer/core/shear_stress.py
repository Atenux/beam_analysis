"""
shear_stress.py
---------------
Transverse (flexural) shear-stress distribution through a cross-section using
the classic formula:

    tau(z) = V * Q(z) / (Iyy * t(z))

where, for a horizontal cut at height z (section-local Z is vertical):
    V      - transverse shear force (in the vertical / Z direction)
    Q(z)   - first moment, about the centroidal horizontal axis, of the area of
             the section above the cut: integral over (z' > z) of (z' - zc) dA
    Iyy    - second moment of area about the centroidal horizontal axis
    t(z)   - total section width at height z (sum of segment lengths where the
             horizontal line z = const crosses the section; holes excluded)

All geometry is scaled by ``length_factor`` first so that the result is reported
in the display unit system (e.g. N + mm -> MPa, lbf + in -> psi).
"""

from __future__ import annotations

import numpy as np
from shapely.geometry import Polygon, MultiPolygon, LineString, box
from shapely.ops import unary_union
import shapely.affinity as affinity

from beam_analyzer.core.section_props import _ring_properties, properties_from_polygons


def _as_polygons(geom) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def _area_and_first_moment(geom) -> tuple[float, float]:
    """Return (A, Sy) where Sy = integral of z dA, summing exteriors and holes."""
    A_tot = 0.0
    Sy_tot = 0.0
    for poly in _as_polygons(geom):
        ext = np.array(poly.exterior.coords)
        if Polygon(ext).exterior.is_ccw is False:
            ext = ext[::-1]
        A_e, Sy_e, *_ = _ring_properties(ext[:-1])
        A_tot += A_e
        Sy_tot += Sy_e
        for interior in poly.interiors:
            ring = np.array(interior.coords)
            if Polygon(ring).exterior.is_ccw is True:
                ring = ring[::-1]
            A_h, Sy_h, *_ = _ring_properties(ring[:-1])
            A_tot += A_h
            Sy_tot += Sy_h
    return A_tot, Sy_tot


def shear_stress_profile(polygons: list[Polygon], V: float,
                         length_factor: float = 1.0,
                         n: int = 81) -> dict:
    """Compute the transverse shear-stress distribution through the depth.

    Returns a dict with arrays ``z`` (vertical coordinate, display units),
    ``tau`` (shear stress), ``t`` (width), ``Q`` (first moment), plus scalars
    ``zc``, ``Iyy``, ``tau_max`` (peak magnitude) and ``z_at_max``.
    """
    scaled = [
        affinity.scale(p, xfact=length_factor, yfact=length_factor, origin=(0, 0))
        for p in polygons
    ]
    props = properties_from_polygons(scaled)
    Iyy = props.Iyy
    zc = props.zc

    merged = unary_union(scaled)
    y_min, z_min, y_max, z_max = merged.bounds
    pad = (y_max - y_min) * 0.5 + 1.0

    zs = np.linspace(z_min, z_max, n)
    taus = np.full(n, np.nan)
    widths = np.zeros(n)
    Qs = np.zeros(n)

    upper_box_top = z_max + abs(z_max - z_min) + 1.0
    for i, z in enumerate(zs):
        line = LineString([(y_min - pad, z), (y_max + pad, z)])
        t = merged.intersection(line).length
        widths[i] = t

        clip = merged.intersection(
            box(y_min - pad, z, y_max + pad, upper_box_top))
        if clip.is_empty:
            Q = 0.0
        else:
            A_c, Sy_c = _area_and_first_moment(clip)
            Q = Sy_c - zc * A_c
        Qs[i] = Q

        if t > 1e-9 and abs(Iyy) > 1e-12:
            taus[i] = V * Q / (Iyy * t)

    finite = np.isfinite(taus)
    if finite.any():
        idx = int(np.nanargmax(np.abs(taus)))
        tau_max = float(taus[idx])
        z_at_max = float(zs[idx])
    else:
        tau_max = float("nan")
        z_at_max = float("nan")

    return {
        "z": zs,
        "tau": taus,
        "t": widths,
        "Q": Qs,
        "zc": zc,
        "Iyy": Iyy,
        "tau_max": tau_max,
        "z_at_max": z_at_max,
    }

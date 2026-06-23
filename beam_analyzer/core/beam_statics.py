"""
beam_statics.py
---------------
Statically determinate beam solver. Given supports and applied loads along the
beam (longitudinal) axis, computes the shear-force V(x) and bending-moment M(x)
diagrams. The shear at a station is what feeds the transverse shear-stress
formula tau = V * Q / (I * t).

Sign conventions (all positions along the beam axis, in internal length units):
    - Transverse loads (point loads, distributed loads) are positive DOWNWARD.
    - Support reaction forces are positive UPWARD.
    - Applied point moments and reaction moments are positive COUNTER-CLOCKWISE.
    - Shear V(x): sum of upward forces to the left of the cut (standard diagram).
    - Bending moment M(x): sagging positive.

Supported (determinate) configurations:
    - Two supports  -> simply supported beam (two vertical reactions).
    - One support   -> cantilever (vertical reaction + fixing moment).
Anything else is statically indeterminate and raises ValueError.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np


@dataclass
class PointLoad:
    x: float
    fz: float  # downward positive [force]


@dataclass
class DistLoad:
    x1: float
    x2: float
    w1: float  # intensity at x1, downward positive [force/length]
    w2: float  # intensity at x2


@dataclass
class PointMoment:
    x: float
    m: float  # counter-clockwise positive [force*length]


@dataclass
class BeamSolution:
    x: np.ndarray            # grid of beam-axis positions
    V: np.ndarray            # shear force at each grid point
    M: np.ndarray            # bending moment at each grid point
    reactions: list = field(default_factory=list)   # (x, force) upward positive
    react_moments: list = field(default_factory=list)  # (x, moment) ccw positive
    notes: str = ""

    def shear_at(self, xq: float) -> float:
        return float(np.interp(xq, self.x, self.V))

    def moment_at(self, xq: float) -> float:
        return float(np.interp(xq, self.x, self.M))


def _cumtrapz(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Cumulative trapezoidal integral with a leading zero (length matches x)."""
    if len(x) < 2:
        return np.zeros_like(x)
    incr = 0.5 * (y[1:] + y[:-1]) * np.diff(x)
    return np.concatenate([[0.0], np.cumsum(incr)])


def _dist_intensity(grid: np.ndarray, loads: list[DistLoad]) -> np.ndarray:
    """Total distributed intensity q(s) (downward positive) sampled on grid."""
    q = np.zeros_like(grid)
    for dl in loads:
        lo, hi = min(dl.x1, dl.x2), max(dl.x1, dl.x2)
        if hi - lo < 1e-12:
            continue
        w1, w2 = (dl.w1, dl.w2) if dl.x1 <= dl.x2 else (dl.w2, dl.w1)
        mask = (grid >= lo) & (grid <= hi)
        frac = (grid[mask] - lo) / (hi - lo)
        q[mask] += w1 + (w2 - w1) * frac
    return q


def solve_beam(domain: tuple[float, float],
               supports: list[float],
               point_loads: list[PointLoad] | None = None,
               dist_loads: list[DistLoad] | None = None,
               moments: list[PointMoment] | None = None,
               n: int = 1000) -> BeamSolution:
    """Solve a determinate beam and return its V(x) and M(x) diagrams.

    ``domain`` is (x_lo, x_hi); ``supports`` is a list of beam-axis positions
    (1 -> cantilever, 2 -> simply supported).
    """
    point_loads = point_loads or []
    dist_loads = dist_loads or []
    moments = moments or []

    x_lo, x_hi = float(min(domain)), float(max(domain))
    if x_hi - x_lo < 1e-9:
        raise ValueError("Beam domain has zero length.")

    grid = np.linspace(x_lo, x_hi, n)
    q = _dist_intensity(grid, dist_loads)

    # Cumulative distributed-load integrals along the beam.
    cum_w = _cumtrapz(q, grid)            # total downward load left of x
    cum_ws = _cumtrapz(q * grid, grid)    # first moment of that load about origin
    W_dist = cum_w[-1]
    Mom_dist_o = cum_ws[-1]               # moment of all dist load about origin

    P_tot = sum(pl.fz for pl in point_loads)
    Mom_pt_o = sum(pl.fz * pl.x for pl in point_loads)
    M_applied = sum(pm.m for pm in moments)

    reactions: list[tuple[float, float]] = []     # (x, upward force)
    react_moments: list[tuple[float, float]] = []  # (x, ccw moment)
    notes = ""

    supports = sorted(float(s) for s in supports)

    if len(supports) == 2:
        xa, xb = supports
        if xb - xa < 1e-9:
            raise ValueError("The two supports coincide.")
        # Sum moments about A (ccw positive): downward loads give -(x-xa)*F.
        # (xb-xa)*Rb - sum((xp-xa)*P) - (Mom_dist_o - W_dist*xa) + M_applied = 0
        mom_loads_about_a = (Mom_pt_o - P_tot * xa) + (Mom_dist_o - W_dist * xa)
        Rb = (mom_loads_about_a - M_applied) / (xb - xa)
        Ra = (P_tot + W_dist) - Rb
        reactions = [(xa, Ra), (xb, Rb)]
        notes = "Simply supported"
    elif len(supports) == 1:
        xa = supports[0]
        Ra = P_tot + W_dist
        # Fixing moment from equilibrium about A (ccw reaction couple).
        mom_loads_about_a = (Mom_pt_o - P_tot * xa) + (Mom_dist_o - W_dist * xa)
        Ma = mom_loads_about_a - M_applied
        reactions = [(xa, Ra)]
        react_moments = [(xa, Ma)]
        notes = "Cantilever"
    else:
        raise ValueError(
            f"{len(supports)} supports is statically indeterminate; "
            "use 1 (cantilever) or 2 (simply supported)."
        )

    # Shear: upward forces to the left of each grid point.
    V = -cum_w.copy()
    for (xr, R) in reactions:
        V += R * (grid >= xr)
    for pl in point_loads:
        V -= pl.fz * (grid >= pl.x)

    # Bending moment (sagging positive): moments of all left actions about x.
    # Distributed term: integral q(s)*(x - s) ds = x*cum_w - cum_ws.
    M = -(grid * cum_w - cum_ws)
    for (xr, R) in reactions:
        M += R * np.maximum(grid - xr, 0.0)
    for pl in point_loads:
        M -= pl.fz * np.maximum(grid - pl.x, 0.0)
    for (xr, Cr) in react_moments:        # reaction couple
        M -= Cr * (grid >= xr)
    for pm in moments:                     # applied couple
        M -= pm.m * (grid >= pm.x)

    return BeamSolution(x=grid, V=V, M=M,
                        reactions=reactions, react_moments=react_moments,
                        notes=notes)

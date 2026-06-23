"""
step_slicer.py
--------------
Reads a STEP file, identifies bodies by name, and produces cross-section cuts
at planes perpendicular to the longitudinal X axis.

For each station X it returns Shapely polygons in (Y, Z) coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
import numpy as np
from shapely.geometry import Polygon, MultiPolygon
from shapely.validation import make_valid

from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDF import TDF_LabelSequence, TDF_Label
from OCP.TDataStd import TDataStd_Name
from OCP.TopoDS import TopoDS_Shape, TopoDS, TopoDS_Compound
from OCP.gp import gp_Pnt, gp_Dir, gp_Pln, gp_Ax3, gp_Trsf, gp_Vec, gp_Ax1
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_WIRE, TopAbs_SOLID, TopAbs_FACE
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_UniformAbscissa, GCPnts_QuasiUniformDeflection
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
from OCP.TopTools import TopTools_HSequenceOfShape
from OCP.BRep import BRep_Tool
from OCP.GeomAbs import GeomAbs_Line
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform


def _section_axes(axis: int) -> tuple[int, int]:
    return ((1, 2), (0, 2), (0, 1))[axis]


def _pt_2d(p, axes: tuple[int, int]) -> list[float]:
    c = (p.X(), p.Y(), p.Z())
    return [c[axes[0]], c[axes[1]]]


@dataclass
class NamedShape:
    name: str
    shape: TopoDS_Shape


def read_step_with_names(path: str) -> list[NamedShape]:
    """Read a STEP file using XDE (STEPCAFControl) to preserve body names."""
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)

    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)
    if not reader.ReadFile(path):
        raise RuntimeError(f"Could not read STEP file: {path}")
    reader.Transfer(doc)

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(labels)

    out: list[NamedShape] = []

    def _get_name(label: TDF_Label) -> str:
        attr = TDataStd_Name()
        if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
            return attr.Get().ToExtString()
        return "UNNAMED"

    def _walk(label: TDF_Label, parent_name: str = ""):
        name = _get_name(label)
        full_name = name if not parent_name else f"{parent_name}/{name}"
        if shape_tool.IsReference_s(label):
            ref = TDF_Label()
            if shape_tool.GetReferredShape_s(label, ref):
                _walk(ref, full_name)
                return
        if shape_tool.IsAssembly_s(label):
            children = TDF_LabelSequence()
            shape_tool.GetComponents_s(label, children)
            for i in range(1, children.Length() + 1):
                _walk(children.Value(i), full_name)
            return
        shp = shape_tool.GetShape_s(label)
        if shp is not None and not shp.IsNull():
            out.append(NamedShape(name=full_name, shape=shp))

    for i in range(1, labels.Length() + 1):
        _walk(labels.Value(i))

    if not out:
        from OCP.STEPControl import STEPControl_Reader
        r2 = STEPControl_Reader()
        r2.ReadFile(path)
        r2.TransferRoots()
        shp = r2.OneShape()
        out.append(NamedShape(name="ALL", shape=shp))

    expanded: list[NamedShape] = []
    for ns in out:
        solids = _enumerate_solids(ns.shape)
        if len(solids) <= 1:
            expanded.append(ns)
            continue
        for idx, sol in enumerate(solids, 1):
            expanded.append(NamedShape(
                name=f"{ns.name}/solid_{idx:03d}", shape=sol))
    return expanded


def _enumerate_solids(shape: TopoDS_Shape) -> list[TopoDS_Shape]:
    """Walk shape and return every TopoDS_Solid found."""
    solids: list[TopoDS_Shape] = []
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        solids.append(TopoDS.Solid_s(exp.Current()))
        exp.Next()
    return solids


def global_bounds(shapes: list[TopoDS_Shape], axis: int = 0) -> tuple[float, float]:
    """Global bounding box along the specified axis (0=X, 1=Y, 2=Z)."""
    bbox = Bnd_Box()
    for s in shapes:
        BRepBndLib.Add_s(s, bbox)
    if bbox.IsVoid():
        return (0.0, 0.0)
    vals = bbox.Get()
    return vals[axis], vals[axis + 3]


def _sample_edge_2d(edge, axes: tuple[int, int] = (1, 2),
                    deflection: float = 0.5) -> np.ndarray:
    """Sample an edge projected onto two coordinate axes. Returns array (N, 2)."""
    curve = BRepAdaptor_Curve(edge)
    if curve.GetType() == GeomAbs_Line:
        u1, u2 = curve.FirstParameter(), curve.LastParameter()
        p1 = curve.Value(u1)
        p2 = curve.Value(u2)
        return np.array([_pt_2d(p1, axes), _pt_2d(p2, axes)])
    sampler = GCPnts_QuasiUniformDeflection(curve, deflection)
    if not sampler.IsDone() or sampler.NbPoints() < 2:
        n = 24
        us = np.linspace(curve.FirstParameter(), curve.LastParameter(), n)
        pts = [curve.Value(float(u)) for u in us]
        return np.array([_pt_2d(p, axes) for p in pts])
    pts = []
    for i in range(1, sampler.NbPoints() + 1):
        pts.append(_pt_2d(sampler.Value(i), axes))
    return np.array(pts)


def _wire_to_ring(wire, axes: tuple[int, int] = (1, 2),
                  deflection: float = 0.5) -> np.ndarray | None:
    """Traverse edges of a wire and return concatenated 2D points."""
    exp = TopExp_Explorer(wire, TopAbs_EDGE)
    coords: list[np.ndarray] = []
    while exp.More():
        edge = TopoDS.Edge_s(exp.Current())
        pts = _sample_edge_2d(edge, axes=axes, deflection=deflection)
        if coords:
            last = coords[-1][-1]
            d_start = np.linalg.norm(pts[0] - last)
            d_end = np.linalg.norm(pts[-1] - last)
            if d_end < d_start:
                pts = pts[::-1]
            coords.append(pts[1:])
        else:
            coords.append(pts)
        exp.Next()
    if not coords:
        return None
    ring = np.vstack(coords)
    return ring if ring.shape[0] >= 3 else None


def _ring_perimeter(ring: np.ndarray) -> float:
    return float(np.linalg.norm(np.diff(ring, axis=0), axis=1).sum())


def _flatten_polygons(geom) -> list[Polygon]:
    """Extract all simple polygons from geom."""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom] if geom.area > 1e-9 else []
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if g.area > 1e-9]
    out: list[Polygon] = []
    for g in getattr(geom, "geoms", []):
        out.extend(_flatten_polygons(g))
    return out


def _edges_to_polygons(edges: list, axes: tuple[int, int] = (1, 2),
                        deflection: float = 0.5,
                        gap_frac_tol: float = 0.05,
                        min_area: float = 1e-6) -> list[Polygon]:
    """Connect edges into closed wires and return Shapely polygons with holes."""
    if not edges:
        return []

    seq = TopTools_HSequenceOfShape()
    for e in edges:
        seq.Append(e)

    wires_seq = TopTools_HSequenceOfShape()
    ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(seq, 1e-4, False, wires_seq)

    raw_polys: list[Polygon] = []
    for i in range(1, wires_seq.Length() + 1):
        ring = _wire_to_ring(wires_seq.Value(i), axes=axes, deflection=deflection)
        if ring is None:
            continue
        gap = float(np.linalg.norm(ring[0] - ring[-1]))
        perim = _ring_perimeter(ring)
        if gap > 1e-9:
            if perim <= 0 or gap / perim > gap_frac_tol:
                continue
            ring = np.vstack([ring, ring[0:1]])

        try:
            cleaned = make_valid(Polygon(ring))
        except Exception:
            continue
        raw_polys.extend(_flatten_polygons(cleaned))

    raw_polys = [p for p in raw_polys if p.area > min_area]
    if not raw_polys:
        return []
    if len(raw_polys) == 1:
        return raw_polys

    reps = [p.representative_point() for p in raw_polys]
    bboxes = [p.bounds for p in raw_polys]
    nesting = [0] * len(raw_polys)
    for j in range(len(raw_polys)):
        bj = bboxes[j]
        for i in range(len(raw_polys)):
            if i == j:
                continue
            bi = bboxes[i]
            if (bi[0] > bj[0] or bi[1] > bj[1]
                    or bi[2] < bj[2] or bi[3] < bj[3]):
                continue
            if raw_polys[i].contains(raw_polys[j]):
                nesting[j] += 1

    holes_by_parent: dict[int, list[int]] = {}
    for j in range(len(raw_polys)):
        if nesting[j] % 2 == 0:
            continue
        parent_depth = nesting[j] - 1
        candidates = [
            i for i in range(len(raw_polys))
            if i != j
            and nesting[i] == parent_depth
            and raw_polys[i].contains(reps[j])
        ]
        if not candidates:
            nesting[j] = parent_depth
            continue
        parent = min(candidates, key=lambda i: raw_polys[i].area)
        holes_by_parent.setdefault(parent, []).append(j)

    result: list[Polygon] = []
    for i in range(len(raw_polys)):
        if nesting[i] % 2 != 0:
            continue
        outer = raw_polys[i]
        hole_idxs = holes_by_parent.get(i, [])
        if hole_idxs:
            holes = [list(raw_polys[h].exterior.coords) for h in hole_idxs]
            built = Polygon(list(outer.exterior.coords), holes=holes)
            if not built.is_valid:
                built = make_valid(built)
            for part in _flatten_polygons(built):
                if part.area > min_area:
                    result.append(part)
        elif outer.area > min_area:
            result.append(outer)
    return result


def slice_shape_at(shape: TopoDS_Shape, station: float,
                   axis: int = 0, deflection: float = 0.5) -> list[Polygon]:
    """Cut shape with a plane perpendicular to the given axis at the station value."""
    origin = [0.0, 0.0, 0.0]
    origin[axis] = station
    normal = [0.0, 0.0, 0.0]
    normal[axis] = 1.0
    plane = gp_Pln(gp_Ax3(gp_Pnt(*origin), gp_Dir(*normal)))
    section = BRepAlgoAPI_Section(shape, plane)
    section.ComputePCurveOn1(False)
    section.Approximation(True)
    section.Build()
    if not section.IsDone():
        return []
    result = section.Shape()
    edges = []
    exp = TopExp_Explorer(result, TopAbs_EDGE)
    while exp.More():
        edges.append(TopoDS.Edge_s(exp.Current()))
        exp.Next()
    sec = _section_axes(axis)
    return _edges_to_polygons(edges, axes=sec, deflection=deflection)


@dataclass
class StationCut:
    x: float
    body_name: str = ""
    polygons: list[Polygon] = field(default_factory=list)

    def all_polygons(self) -> list[Polygon]:
        return self.polygons


def slice_assembly(named_shapes: list[NamedShape],
                   x_stations: list[float],
                   axis: int = 0,
                   deflection: float = 0.5) -> list[StationCut]:
    """Cut each body at each station and group polygons."""
    cuts: list[StationCut] = []
    for x in x_stations:
        cut = StationCut(x=x)
        for ns in named_shapes:
            polys = slice_shape_at(ns.shape, x, axis=axis, deflection=deflection)
            if polys:
                cut.body_name = ns.name
                cut.polygons.extend(polys)
        cuts.append(cut)
    return cuts


# ===========================================================================
# Side view image generation (X-Z projection with isometric transform)
# ===========================================================================

def _collect_all_edges(shape: TopoDS_Shape) -> list:
    """Collect all edges from a shape (any nesting depth)."""
    edges = []
    exp = TopExp_Explorer(shape, TopAbs_EDGE)
    while exp.More():
        edges.append(TopoDS.Edge_s(exp.Current()))
        exp.Next()
    return edges


def generate_side_view_image(named_shapes: list[NamedShape],
                              output_path: str,
                              axis: int = 0,
                              deflection: float = 0.5,
                              dpi: int = 150,
                              line_width: float = 0.5,
                              line_color: str = "#333333",
                              margin: float = 0.05) -> dict:
    """Generate a 2D side view (X-Z projection) of all shapes and save as PNG.

    The image is rendered with explicit axis limits matching the geometry
    bounding box, so it can be overlaid on the side view plot using
    matplotlib's ``imshow(..., extent=(xmin, xmax, zmin, zmax))``.

    Returns dict with 'xlim', 'ylim', 'width_px', 'height_px', 'path'.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    all_edges: list = []
    for ns in named_shapes:
        all_edges.extend(_collect_all_edges(ns.shape))

    if not all_edges:
        raise ValueError("No edges found in STEP file.")

    sec = _section_axes(axis)
    side_axes = (axis, sec[1])

    all_pts = []
    for edge in all_edges:
        pts = _sample_edge_2d(edge, axes=side_axes, deflection=deflection)
        all_pts.append(pts)
    combined = np.vstack(all_pts)
    x_min, z_min = combined.min(axis=0)
    x_max, z_max = combined.max(axis=0)

    dx = x_max - x_min
    dz = z_max - z_min
    if dx < 1e-9:
        dx = 1.0
    if dz < 1e-9:
        dz = 1.0

    x_pad = dx * margin
    z_pad = dz * margin
    xlim = (x_min - x_pad, x_max + x_pad)
    ylim = (z_min - z_pad, z_max + z_pad)

    data_w = xlim[1] - xlim[0]
    data_h = ylim[1] - ylim[0]
    aspect = data_w / data_h

    fig_h_in = 6.0
    fig_w_in = fig_h_in * aspect
    fig, ax = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=dpi)

    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_aspect("equal")
    ax.axis("off")

    for pts in all_pts:
        if pts.shape[0] >= 2:
            ax.plot(pts[:, 0], pts[:, 1], color=line_color, lw=line_width, alpha=0.7)

    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    fig.savefig(output_path, dpi=dpi,
                facecolor="white", edgecolor="none")
    plt.close(fig)

    width_px = int(fig_w_in * dpi)
    height_px = int(fig_h_in * dpi)

    return {
        "xlim": xlim,
        "ylim": ylim,
        "width_px": width_px,
        "height_px": height_px,
        "path": output_path,
    }

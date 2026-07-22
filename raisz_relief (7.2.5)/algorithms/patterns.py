# -*- coding: utf-8 -*-
# This file is part of <Raisz Relief Plugin>.
#
# Copyright (C) 2026 <Maksim Boiko>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
patterns.py -- hydrography patterns and land cover textures in the
physiographic map style. They return geometry IN MAP COORDINATES
(meters), which compose converts to the displaced screen via to_screen.

Spacings/bands are in meters. Hydrography (compose.draw_area_waters):
  coastal_vignette -- sea shore band; lake_hatch -- lake hatching;
  marsh_tufts -- marsh symbols.
Land cover (compose.draw_landcover):
  forest_points/sand_points -> (xy, sizes); ice_lines/scrub_tufts/grass_tufts
  -> lists of segments.

Dependency: shapely.
"""

import numpy as np

from .grid import as_rings

from qgis.core import QgsMessageLog

def _poly(ring):
    """Rings [outer, hole1, ...] (or a single ring) -> Polygon.

    Holes are handed to shapely, so the patterns respect them: lake
    hatching and marsh symbols stay off the islands, vignettes and form
    lines also follow the inner shores."""
    from shapely.geometry import Polygon
    try:
        rings = as_rings(ring)
        if not rings or len(rings[0]) < 3:
            return None
        holes = [np.asarray(h) for h in rings[1:] if len(h) >= 3]
        p = Polygon(np.asarray(rings[0]), holes)
        if not p.is_valid:
            p = p.buffer(0)
        return p if (not p.is_empty and p.area > 0) else None
    except Exception:
        return None


def _geoms(g):
    if g is None or g.is_empty:
        return []
    return list(g.geoms) if hasattr(g, "geoms") else [g]


def _sample_points(poly, spacing, jitter=0.45, seed=17):
    """Staggered-grid points with jitter inside the polygon (prepared)."""
    from shapely import contains_xy
    rng = np.random.RandomState(seed)
    minx, miny, maxx, maxy = poly.bounds
    xs = np.arange(minx + spacing * 0.5, maxx, spacing)
    ys = np.arange(miny + spacing * 0.5, maxy, spacing)
    if len(xs) == 0 or len(ys) == 0:
        return np.empty((0, 2))
    pts = []
    for j, y in enumerate(ys):
        off = (spacing * 0.5) if (j % 2) else 0.0
        xrow = xs + off
        X = xrow + (rng.rand(len(xrow)) - 0.5) * 2 * jitter * spacing
        Y = np.full(len(xrow), y) + (rng.rand(len(xrow)) - 0.5) * 2 * jitter * spacing
        ins = contains_xy(poly, X, Y)
        if ins.any():
            pts.append(np.column_stack([X[ins], Y[ins]]))
    return np.vstack(pts) if pts else np.empty((0, 2))


# --------------------------- hydrography ----------------------------------

def coastal_vignette(rings, step, n=3, extent=None, min_island=2.0,
                     edges=None):
    """n concentric lines inward from the shore, step in meters.
    extent=(xmin,ymin,xmax,ymax): band sections along the DEM frame
    (artificial edges) are cut away, keeping only the band along the
    true coastline.

    edges: extra artificial edges -- rings of the areas without data
    (nodata). Their border is not a shore but the same survey cut as the
    frame, so no band is drawn along it.

    min_island: islands (holes) smaller than (min_island*step)^2 take no
    part in the band -- the band is wider than they are, and every extra
    ring makes the boundary and all buffers heavier."""
    from shapely.geometry import box, Polygon, LineString
    # The band is the outline pushed inward by step*k. A section produced
    # by the artificial edge of the territory lies step*k from the FRAME,
    # a section from a real shore lies step*k from the shore; the two sets
    # complement each other. Previously the selection went through
    # coast.buffer() on the shore: on a polygon with hundreds of islands
    # one such buffer costs ~15 s. The frame, by contrast, is a rectangle
    # and its buffer is computed once per call.
    zones = [None] * n
    art = []
    if extent is not None:
        xmin, ymin, xmax, ymax = extent
        art.append(box(xmin, ymin, xmax, ymax).boundary)
    for e in (edges or []):
        for r in as_rings(e):
            a = np.asarray(r, dtype="float64")
            if len(a) >= 2:
                art.append(LineString(a))
    if art:
        if len(art) == 1:
            edge_geom = art[0]
        else:
            from shapely.ops import unary_union
            edge_geom = unary_union(art)
        zones = [edge_geom.buffer(step * k + step * 0.25)
                 for k in range(1, n + 1)]
    out = []
    amin = (float(min_island) * step) ** 2
    for ring in rings:
        poly = _poly(ring)
        if poly is None:
            continue
        # drop tiny islands FROM THE BAND GEOMETRY (not from the fill!)
        if poly.interiors and amin > 0:
            keep_h = [h for h in poly.interiors if Polygon(h).area >= amin]
            if len(keep_h) != len(poly.interiors):
                try:
                    poly = Polygon(poly.exterior, keep_h)
                except Exception as e:
                    QgsMessageLog.logMessage(str(e), "RaiszRelief")
                if poly.is_empty:
                    continue
        for k in range(1, n + 1):
            zone = zones[k - 1]
            for g in _geoms(poly.buffer(-step * k)):
                if g.geom_type != "Polygon" or g.exterior is None:
                    continue
                # outer shore + island (hole) shores: the band runs around
                # every island, as on hand-drawn maps
                for ering in [g.exterior] + list(g.interiors):
                    if zone is None:
                        out.append(np.asarray(ering.coords))
                        continue
                    keep = ering.difference(zone)
                    for gg in _geoms(keep):
                        if (gg.geom_type in ("LineString", "LinearRing")
                                and gg.length > 0):
                            out.append(np.asarray(gg.coords))
    return out


def lake_hatch(rings, spacing, angle_deg=0.0):
    """Parallel hatching inside polygons, spacing in meters."""
    from shapely.geometry import LineString
    from shapely.affinity import rotate
    out = []
    for ring in rings:
        poly = _poly(ring)
        if poly is None:
            continue
        work = rotate(poly, -angle_deg, origin="centroid") if angle_deg else poly
        minx, miny, maxx, maxy = work.bounds
        y = miny + spacing
        while y < maxy:
            seg = work.intersection(LineString([(minx - 1, y), (maxx + 1, y)]))
            for g in _geoms(seg):
                if g.geom_type == "LineString" and g.length > 0:
                    ln = rotate(g, angle_deg, origin=poly.centroid) if angle_deg else g
                    out.append(np.asarray(ln.coords))
            y += spacing
    return out


def marsh_tufts(rings, spacing, size=None):
    """Marsh symbols: a short horizontal dash + 3 grass blades above."""
    s = size if size else spacing * 0.32
    out = []
    for ring in rings:
        poly = _poly(ring)
        if poly is None:
            continue
        for x, y in _sample_points(poly, spacing, jitter=0.35, seed=5):
            out.append(np.array([[x - s, y], [x + s, y]]))
            for dx in (-s * 0.6, 0.0, s * 0.6):
                out.append(np.array([[x + dx, y], [x + dx, y + s * 1.3]]))
    return out


# --------------------------- land cover -----------------------------------

def forest_points(rings, spacing, seed=12):
    """Tree crowns -> (xy Nx2, sizes N) with a slight size scatter."""
    rng = np.random.RandomState(seed)
    xy = []
    for ring in rings:
        poly = _poly(ring)
        if poly is None:
            continue
        p = _sample_points(poly, spacing, jitter=0.5, seed=seed)
        if len(p):
            xy.append(p)
    if not xy:
        return np.empty((0, 2)), np.empty((0,))
    xy = np.vstack(xy)
    return xy, 0.7 + 0.6 * rng.rand(len(xy))


def sand_points(rings, spacing, seed=7):
    """Sand/dunes: fine uniform speckle -> (xy, sizes=const)."""
    xy = []
    for ring in rings:
        poly = _poly(ring)
        if poly is None:
            continue
        p = _sample_points(poly, spacing, jitter=0.6, seed=seed)
        if len(p):
            xy.append(p)
    if not xy:
        return np.empty((0, 2)), np.empty((0,))
    xy = np.vstack(xy)
    return xy, np.full(len(xy), 0.55)


def ice_lines(rings, step, n=4):
    """Ice/glaciers: concentric form lines inward from the edge."""
    return coastal_vignette(rings, step, n)


def scrub_tufts(rings, spacing, size=None, seed=21):
    """Scrub: sparse open chevrons (two short slanted dashes)."""
    s = size if size else spacing * 0.28
    out = []
    for ring in rings:
        poly = _poly(ring)
        if poly is None:
            continue
        for x, y in _sample_points(poly, spacing, jitter=0.4, seed=seed):
            out.append(np.array([[x - s, y], [x, y + s * 1.1]]))
            out.append(np.array([[x + s, y], [x, y + s * 1.1]]))
    return out


def grass_tufts(rings, spacing, size=None, seed=33):
    """Grassland/steppe: a tuft of 3 short vertical dashes."""
    s = size if size else spacing * 0.30
    out = []
    for ring in rings:
        poly = _poly(ring)
        if poly is None:
            continue
        for x, y in _sample_points(poly, spacing, jitter=0.45, seed=seed):
            for dx in (-s * 0.5, 0.0, s * 0.5):
                h = s * (1.0 + 0.3 * (dx == 0.0))
                out.append(np.array([[x + dx, y], [x + dx, y + h]]))
    return out

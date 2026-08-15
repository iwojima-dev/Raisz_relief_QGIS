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
compose.py -- shared overlay primitives for both cores (hybrid and
classic): blitting the draped fill and drawing waters/roads/settlements
in displaced coordinates with styles from theme.resolve(). Lines hidden
behind mountains are cut by the vis mask.
"""

import numpy as np
from scipy import ndimage
from matplotlib.collections import LineCollection
import matplotlib.patheffects as path_effects

from .grid import world_to_pixel, as_rings


def _disp_at(disp, r, c):
    rows, cols = disp.shape
    return ndimage.map_coordinates(
        disp, [np.clip(r, 0, rows - 1), np.clip(c, 0, cols - 1)],
        order=1, mode="nearest")


_DISP_SCALE = None   # (sr, sc, mul) for decoration in strip mode; None = normal


def set_disp_scale(s):
    """Set the disp-field scale for to_screen (strip mode) or clear it (None).
    s=(sr,sc,mul): sample disp at (row*sr, col*sc) and multiply by mul,
    to draw decoration over the DOWNSAMPLED disp in full-sheet coordinates."""
    global _DISP_SCALE
    _DISP_SCALE = s


def to_screen(xy, geff, disp):
    """Map (N,2) -> screen (col, screen_y)."""
    pc = world_to_pixel(xy, geff)
    col, row = pc[:, 0], pc[:, 1]
    if _DISP_SCALE is None:
        d = _disp_at(disp, row, col)
    else:
        sr, sc, mul = _DISP_SCALE
        d = _disp_at(disp, row * sr, col * sc) * mul
    sy = row - d
    return col, row, sy


def _vis_at(vis, r, c):
    """Visibility at a point. In strip mode the mask is downsampled while
    the coordinates arrive in full-sheet space -- rescale them the same way
    to_screen does via _DISP_SCALE. Without this a downsampled mask cannot
    be passed here at all, and strip-mode decoration was left with no
    hidden-line clipping whatsoever."""
    rows, cols = vis.shape
    if _DISP_SCALE is not None:
        sr, sc, _mul = _DISP_SCALE
        r = np.asarray(r, dtype="float64") * sr
        c = np.asarray(c, dtype="float64") * sc
    rr = np.clip(np.round(r).astype(int), 0, rows - 1)
    cc = np.clip(np.round(c).astype(int), 0, cols - 1)
    return vis[rr, cc]


def blit_fill(ax, img, extent, z=1):
    if img is not None:
        ax.imshow(img, extent=extent, origin="upper",
                  interpolation="bilinear", zorder=z, aspect="auto")


def draw_lines(ax, lines, geff, disp, color, lw, z, alpha=1.0,
               linestyle="-", vis=None):
    """Lines in displaced coordinates; with vis, segments hidden behind mountains are cut."""
    segs = []
    for ln in lines:
        if len(ln) < 2:
            continue
        col, row, sy = to_screen(ln, geff, disp)
        if vis is not None:
            v = _vis_at(vis, row, col)
            pair = v[:-1] & v[1:]
            if not pair.any():
                continue
            p0 = np.column_stack([col[:-1], sy[:-1]])[pair]
            p1 = np.column_stack([col[1:], sy[1:]])[pair]
            for a, b in zip(p0, p1):
                segs.append([a, b])
        else:
            segs.append(np.column_stack([col, sy]))
    if segs:
        ax.add_collection(LineCollection(
            segs, colors=[color], linewidths=lw, alpha=alpha,
            linestyles=linestyle, capstyle="round", zorder=z))
    return len(segs)


def draw_polys(ax, polys, geff, disp, z, face=None, edge=None, lw=0.4,
               alpha=1.0):
    """Decoration polygons. Each item is rings [outer, hole1, ...]
    (as_rings also accepts a "flat" ring). Holes are cut out, so islands
    in seas/lakes/ice caps do not sink."""
    return draw_poly_holes(ax, [as_rings(p) for p in polys], geff, disp, z,
                           face=face, edge=edge, lw=lw, alpha=alpha)


def draw_poly_holes(ax, polys, geff, disp, z, face=None, edge=None, lw=0.4,
                    alpha=1.0):
    """Polygons with holes (islands): each item is a list of rings
    [exterior, hole1, ...]. A compound Path; holes are cut out (islands stay visible)."""
    from matplotlib.path import Path
    from matplotlib.patches import PathPatch
    n = 0
    for rings in polys:
        verts = []; codes = []
        for ring in rings:
            if len(ring) < 3:
                continue
            col, row, sy = to_screen(np.asarray(ring), geff, disp)
            pts = np.column_stack([col, sy])
            verts.extend(pts.tolist()); verts.append(pts[0].tolist())
            codes.append(Path.MOVETO)
            codes.extend([Path.LINETO] * (len(pts) - 1))
            codes.append(Path.CLOSEPOLY)
        if not verts:
            continue
        ax.add_patch(PathPatch(
            Path(verts, codes), facecolor=(face if face else "none"),
            edgecolor=(edge if edge else "none"), linewidth=lw, alpha=alpha,
            zorder=z, antialiased=True))
        n += 1
    return n


def draw_points(ax, pts, geff, disp, z, color, size, label_color,
                label_size=9, vis=None, halo=None, label_font=None,
                label_dx=3.0, marker_lw=0.4):
    if not pts:
        return 0
    xy = np.array([[p[0], p[1]] for p in pts], dtype="float64")
    col, row, sy = to_screen(xy, geff, disp)
    keep = np.ones(len(pts), bool)
    if vis is not None:
        keep = _vis_at(vis, row, col)
    if keep.any():
        # marker edge in the paper colour, like the label halo; a hard
        # white edge stood out on sepia, blueprint and other presets
        ax.scatter(col[keep], sy[keep], s=size, c=color, marker="s",
                   edgecolors=(halo if halo else "white"),
                   linewidths=marker_lw, zorder=z)
    for (x, y, lab), cx, cy, k in zip(pts, col, sy, keep):
        if lab and k:
            pe = ([path_effects.withStroke(
                linewidth=max(2.6, 2.6 * label_size / 9.0), foreground=halo)]
                if halo else None)
            ax.text(cx + label_dx, cy - label_dx, lab, fontsize=label_size,
                    fontfamily=label_font,
                    color=label_color, zorder=z + 1, ha="left", va="bottom",
                    path_effects=pe)
    return int(keep.sum())


def draw_map_segments(ax, segs, geff, disp, color, lw, z, alpha=1.0, vis=None):
    """A list of Nx2 segments in map coordinates -> the displaced screen.
    With vis, segments whose first node is hidden behind mountains are dropped."""
    out = []
    for s in segs:
        if len(s) < 2:
            continue
        col, row, sy = to_screen(np.asarray(s), geff, disp)
        if vis is not None and not _vis_at(vis, row[:1], col[:1])[0]:
            continue
        out.append(np.column_stack([col, sy]))
    if out:
        ax.add_collection(LineCollection(
            out, colors=[color], linewidths=lw, alpha=alpha,
            capstyle="round", zorder=z))
    return len(out)


def draw_map_points(ax, xy, sizes, geff, disp, color, base, z, alpha=1.0,
                    vis=None):
    """Dot texture (crowns/speckle) in map coordinates -> the screen."""
    if xy is None or len(xy) == 0:
        return 0
    col, row, sy = to_screen(np.asarray(xy), geff, disp)
    keep = np.ones(len(xy), bool)
    if vis is not None:
        keep = _vis_at(vis, row, col)
    if not keep.any():
        return 0
    s = (np.asarray(sizes) * base) ** 2
    ax.scatter(col[keep], sy[keep], s=s[keep], c=color, alpha=alpha,
               linewidths=0, marker="o", zorder=z)
    return int(keep.sum())


def hidden_geometry(vis, geff, min_cells=64, log=None):
    """Merged geometry (shapely) of the invisible zones, or None.

    Computed ONCE per render and handed to every area layer: building the
    rings and the unary_union is the expensive part (measured on the fjord
    scene 2702x755: rings 0.5 s, union 1.5 s, the subtraction itself from
    94 sea polygons 0.4 s)."""
    if vis is None or vis.all():
        return None
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from . import grid as gridmod
    rings = gridmod.hidden_polygons(vis, geff, min_cells=min_cells)
    if not rings:
        return None
    polys = []
    for r in rings:
        try:
            p = Polygon(r[0], [h for h in r[1:] if len(h) >= 3])
            if not p.is_valid:
                p = p.buffer(0)
            if not p.is_empty:
                polys.append(p)
        except Exception:  # nosec B110 -- skip a degenerate ring
            pass
    if not polys:
        return None
    geom = unary_union(polys)
    if log:
        log("Hidden zones: %d rings, %.1f%% of sheet area"
            % (len(polys), 100.0 * geom.area
               / max(abs(geff[1] * geff[5]) * vis.size, 1e-9)))
    return geom


def _geom_to_rings(geom):
    """shapely Polygon/MultiPolygon -> list of items [outer, hole...]."""
    out = []
    if geom is None or geom.is_empty:
        return out
    parts = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for g in parts:
        if g.geom_type != "Polygon" or g.exterior is None or g.area <= 0:
            continue
        rings = [np.asarray(g.exterior.coords, dtype="float64")]
        for h in g.interiors:
            rings.append(np.asarray(h.coords, dtype="float64"))
        out.append(rings)
    return out


def clip_polys(items, hidden):
    """Cut from area objects whatever is occluded behind mountains.

    Returns items in the same "rings with holes" format that draw_polys /
    draw_poly_holes understand: difference is exactly what produces holes
    where a mountain covers the middle of a bay."""
    if hidden is None:
        return items
    from shapely.geometry import Polygon
    out = []
    for item in items:
        rings = as_rings(item)
        if not rings or len(rings[0]) < 3:
            continue
        try:
            p = Polygon(rings[0], [h for h in rings[1:] if len(h) >= 3])
            if not p.is_valid:
                p = p.buffer(0)
            if p.is_empty:
                continue
            out.extend(_geom_to_rings(p.difference(hidden)))
        except Exception:  # nosec B110 -- keep broken geometry as-is
            out.append(rings)
    return out


def draw_area_waters(ax, overlays, geff, disp, styles, z0=2, pat=None,
                     vis=None, hidden=None):
    """Area waters (seas, lakes, marshes) -- drawn BEFORE the hachures.
    pat: a dict of pattern parameters or None (patterns off).
    vis: visibility mask for the pattern lines.
    hidden: geometry of the invisible zones (hidden_geometry) -- the
    polygon FILL is clipped by it.

    Patterns (vignette, hatch, tufts) are computed on the ORIGINAL,
    unclipped polygons and cut as lines by vis. Otherwise the vignette
    would run along the clip line, i.e. outline the mountain silhouette
    mistaking it for a shore."""
    def _vp(items):
        """Clip the fill by the invisible zones."""
        return clip_polys(items, hidden)

    n = {}
    for key, sty in (("sea", styles["sea"]), ("marsh", styles["marsh"]),
                     ("lake", styles["lake"])):
        n[key] = draw_polys(ax, _vp(overlays.get(key, [])), geff, disp, z=z0,
                            face=sty["face"], edge=sty["edge"],
                            lw=sty["lw"], alpha=sty["alpha"])
    n["settle_poly"] = draw_polys(
        ax, _vp(overlays.get("settle_poly", [])), geff, disp, z=z0,
        face="#c9b89a", edge="#8a7350", lw=0.3, alpha=0.6)

    sea_auto = overlays.get("sea_auto", [])
    if sea_auto:
        s_sty = styles["sea"]
        n["sea_auto"] = draw_poly_holes(
            ax, _vp(sea_auto), geff, disp, z=z0, face=s_sty["face"],
            edge=s_sty["edge"], lw=s_sty["lw"], alpha=s_sty["alpha"])

    if pat and pat.get("enable"):
        from . import patterns as P
        # the layer and auto-sea now share one format (rings with holes):
        # the vignette also follows island shores
        seas = list(overlays.get("sea", [])) + list(sea_auto)
        lakes = overlays.get("lake", [])
        marsh = overlays.get("marsh", [])
        if seas:
            segs = P.coastal_vignette(seas, pat["vignette_step"],
                                      pat.get("vignette_n", 3),
                                      extent=pat.get("extent"),
                                      edges=overlays.get("nodata_edges"))
            draw_map_segments(ax, segs, geff, disp, styles["sea"]["edge"],
                              lw=0.4, z=z0 + 1, alpha=0.55, vis=vis)
        if lakes:
            segs = P.lake_hatch(lakes, pat["hatch_spacing"])
            draw_map_segments(ax, segs, geff, disp, styles["lake"]["edge"],
                              lw=0.3, z=z0 + 1, alpha=0.5, vis=vis)
        if marsh:
            segs = P.marsh_tufts(marsh, pat["marsh_spacing"])
            draw_map_segments(ax, segs, geff, disp, styles["marsh"]["edge"],
                              lw=0.5, z=z0 + 1, alpha=0.75, vis=vis)
    return n


def draw_infrastructure(ax, overlays, geff, disp, styles, vis=None, z0=7):
    """Rivers, roads, point settlements -- drawn AFTER the hachures."""
    n = {}
    rs = styles["river"]
    # rivers BELOW area waters (z0=6): the zero-level auto-sea covers them;
    # but above the strokes (zorder=5)
    n["river"] = draw_lines(ax, overlays.get("river", []), geff, disp,
                            color=rs["color"], lw=rs["lw"], z=z0 - 1.5,
                            alpha=rs["alpha"], vis=vis)
    roads = overlays.get("road", [])
    ro = styles["road"]
    draw_lines(ax, roads, geff, disp, color=ro["casing"], lw=ro["casing_lw"],
               z=z0 + 1, vis=vis)
    n["road"] = draw_lines(ax, roads, geff, disp, color=ro["core"],
                           lw=ro["core_lw"], z=z0 + 1, vis=vis)
    st = styles["settle"]
    n["settle_pt"] = draw_points(
        ax, overlays.get("settle_pt", []), geff, disp, z=z0 + 2,
        color=st["color"], size=st["size"], label_color=st["label"],
        label_size=st.get("label_size", 9), halo=st.get("halo"), vis=vis,
        label_font=st.get("label_font"), label_dx=st.get("label_dx", 3.0),
        marker_lw=st.get("marker_lw", 0.4))
    return n


def draw_landcover(ax, overlays, geff, disp, styles, lcpat, z0=2, vis=None):
    """Land cover textures (forest, sand, ice, scrub, grassland).
    Drawn ABOVE the hachures (z0=4.5, glyphs z0+1=5.5 > strokes 5),
    but below area waters (6); cut by visibility behind mountains."""
    from . import patterns as P
    lc = styles.get("landcover", {})
    n = {}

    forest = overlays.get("forest", [])
    if forest:
        xy, sz = P.forest_points(forest, lcpat["forest"])
        n["forest"] = draw_map_points(
            ax, xy, sz, geff, disp, lc["forest"]["color"], base=1.5,
            z=z0 + 1, alpha=lc["forest"]["alpha"], vis=vis)

    sand = overlays.get("sand", [])
    if sand:
        xy, sz = P.sand_points(sand, lcpat["sand"])
        n["sand"] = draw_map_points(
            ax, xy, sz, geff, disp, lc["sand"]["color"], base=1.1,
            z=z0 + 1, alpha=lc["sand"]["alpha"], vis=vis)

    ice = overlays.get("ice", [])
    if ice:
        draw_polys(ax, ice, geff, disp, z=z0, face="#f3f6f8",
                   edge=lc["ice"]["color"], lw=0.4, alpha=0.75)
        segs = P.ice_lines(ice, lcpat["ice"], n=4)
        n["ice"] = draw_map_segments(ax, segs, geff, disp, lc["ice"]["color"],
                                     lw=lc["ice"]["lw"], z=z0 + 1,
                                     alpha=lc["ice"]["alpha"], vis=vis)

    scrub = overlays.get("scrub", [])
    if scrub:
        segs = P.scrub_tufts(scrub, lcpat["scrub"])
        n["scrub"] = draw_map_segments(ax, segs, geff, disp,
                                       lc["scrub"]["color"], lw=lc["scrub"]["lw"],
                                       z=z0 + 1, alpha=lc["scrub"]["alpha"], vis=vis)

    grass = overlays.get("grass", [])
    if grass:
        segs = P.grass_tufts(grass, lcpat["grass"])
        n["grass"] = draw_map_segments(ax, segs, geff, disp,
                                       lc["grass"]["color"], lw=lc["grass"]["lw"],
                                       z=z0 + 1, alpha=lc["grass"]["alpha"], vis=vis)
    return n

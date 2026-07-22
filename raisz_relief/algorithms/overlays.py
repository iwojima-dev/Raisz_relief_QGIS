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
overlays.py -- extraction of decoration vector layers (QGIS side).

Every geometry is reprojected to the DEM CRS -> clipped to the DEM
extent -> returned as numpy map coordinates. Pixel binding and the
oblique displacement happen later in the core/fills. Thematic fill
color comes from the QGIS layer style with any renderer
"""

import numpy as np

from qgis.core import (
    QgsCoordinateTransform, QgsProject, QgsRenderContext,
    QgsGeometry, QgsRectangle,
)


def _xform(layer, to_crs):
    src = layer.crs()
    if not src.isValid() or src == to_crs:
        return None
    return QgsCoordinateTransform(src, to_crs, QgsProject.instance())


def _rect_geom(extent):
    if extent is None:
        return None
    xmin, ymin, xmax, ymax = extent
    return QgsGeometry.fromRect(QgsRectangle(xmin, ymin, xmax, ymax))


def _prep(geom, tr, rect):
    """Reproject and clip by the DEM extent rectangle."""
    if geom is None or geom.isEmpty():
        return None
    g = QgsGeometry(geom)
    if tr is not None:
        try:
            g.transform(tr)
        except Exception:
            return None
    if rect is not None:
        g = g.intersection(rect)
        if g is None or g.isEmpty():
            return None
    return g


def _arr(points):
    return np.array([(p.x(), p.y()) for p in points], dtype="float64")


def extract_lines(layer, to_crs, extent=None):
    """Line parts -> a list of (N,2) arrays, clipped to the DEM."""
    if layer is None:
        return []
    tr = _xform(layer, to_crs); rect = _rect_geom(extent)
    res = []
    for f in layer.getFeatures():
        g = _prep(f.geometry(), tr, rect)
        if g is None:
            continue
        parts = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
        for part in parts:
            if part and len(part) >= 2:
                res.append(_arr(part))
    return res


def extract_polys(layer, to_crs, extent=None):
    """Polygons -> a list of rings [outer, hole1, ...] ((N,2) arrays).

    Holes are PRESERVED: without them islands in seas, lakes and ice caps
    sink (a sea polygon floods the skerries and creeps onto the land).
    The consumers -- compose.draw_polys and patterns._poly -- take this
    format."""
    if layer is None:
        return []
    tr = _xform(layer, to_crs); rect = _rect_geom(extent)
    res = []
    for f in layer.getFeatures():
        g = _prep(f.geometry(), tr, rect)
        if g is None:
            continue
        polys = g.asMultiPolygon() if g.isMultipart() else [g.asPolygon()]
        for poly in polys:
            if not poly or len(poly[0]) < 3:
                continue
            rings = [_arr(poly[0])]
            for hole in poly[1:]:
                if hole and len(hole) >= 3:
                    rings.append(_arr(hole))
            res.append(rings)
    return res


def extract_points(layer, to_crs, label_field=None, extent=None):
    """Points -> a list of (x, y, label|None)."""
    if layer is None:
        return []
    tr = _xform(layer, to_crs); rect = _rect_geom(extent)
    fields = [fd.name() for fd in layer.fields()]
    lf = label_field if (label_field and label_field in fields) else None
    res = []
    for f in layer.getFeatures():
        g = _prep(f.geometry(), tr, rect)
        if g is None:
            continue
        pts = g.asMultiPoint() if g.isMultipart() else [g.asPoint()]
        lab = None
        if lf:
            _v = f[lf]
            _t = "" if _v is None else str(_v).strip()
            if _t and _t.upper() != "NULL":
                lab = _t
        for p in pts:
            res.append((p.x(), p.y(), lab))
    return res


def extract_thematic(layer, to_crs, extent=None, default_color="#cccccc"):
    """Thematic polygons -> a list of (rings, '#rrggbb') for rasterization.

    rings = [exterior, hole1, ...] as (x,y) lists. The color is the actual
    feature color from the QGIS layer style (any renderer) via
    """
    if layer is None:
        return []
    tr = _xform(layer, to_crs); rect = _rect_geom(extent)
    renderer = layer.renderer().clone() if layer.renderer() else None
    ctx = QgsRenderContext()
    if renderer is not None:
        try:
            renderer.startRender(ctx, layer.fields())
        except Exception:
            renderer = None
    res = []
    try:
        for f in layer.getFeatures():
            color = default_color
            if renderer is not None:
                try:
                    syms = renderer.symbolsForFeature(f, ctx)
                    if syms:
                        color = syms[0].color().name()
                except Exception:  # nosec B110 -- symbol colour is optional,
                    pass           # default_color is kept on any error
            g = _prep(f.geometry(), tr, rect)
            if g is None:
                continue
            polys = g.asMultiPolygon() if g.isMultipart() else [g.asPolygon()]
            for poly in polys:
                if not poly or len(poly[0]) < 3:
                    continue
                rings = [[(p.x(), p.y()) for p in ring] for ring in poly]
                res.append((rings, color))
    finally:
        if renderer is not None:
            try:
                renderer.stopRender(ctx)
            except Exception:  # nosec B110 -- renderer teardown is
                pass           # best-effort; stop errors are harmless
    return res


# land cover kind by keywords in the field value (RU + EN), order = priority
LANDCOVER_KEYWORDS = [
    ("ice",    ["лёд", "лед", "ледник", "glacier", "ice", "snow", "снег",
                "фирн", "firn", "наледь"]),
    ("salt",   ["солончак", "солён", "солон", "salt", "salar", "плайя",
                "playa", "такыр"]),
    ("sand",   ["песок", "песк", "пещан", "дюн", "бархан", "sand", "dune",
                "пустын", "desert", "эрг"]),
    ("forest", ["лес", "forest", "wood", "древес", "тайга", "taiga", "роща",
                "бор", "дубрав"]),
    ("rock",   ["скал", "осыпь", "осып", "камен", "rock", "scree", "talus",
                "гольц", "останц", "курум", "rubble"]),
    ("grass",  ["трав", "степь", "степн", "луг", "grass", "steppe", "meadow",
                "prairie", "пастбищ", "тундр", "tundra"]),
]


def landcover_kind(value):
    """Field value -> land cover texture kind or None."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    for kind, keys in LANDCOVER_KEYWORDS:
        if any(k in s for k in keys):
            return kind
    return None


def extract_landcover(layer, to_crs, field, extent=None):
    """Land cover polygons -> (items, mapping).

    items: a list of (rings, kind); rings = [exterior, ...] as (x,y) lists.
    mapping: {field_value: kind|'(skipped)'} -- for the matching log.
    """
    if layer is None or not field:
        return [], {}
    fields = [fd.name() for fd in layer.fields()]
    if field not in fields:
        return [], {}
    tr = _xform(layer, to_crs); rect = _rect_geom(extent)
    items = []; mapping = {}
    for f in layer.getFeatures():
        val = f[field]
        kind = landcover_kind(val)
        mapping.setdefault(str(val), kind or "(skipped)")
        if kind is None:
            continue
        g = _prep(f.geometry(), tr, rect)
        if g is None:
            continue
        polys = g.asMultiPolygon() if g.isMultipart() else [g.asPolygon()]
        for poly in polys:
            if not poly or len(poly[0]) < 3:
                continue
            rings = [[(p.x(), p.y()) for p in ring]
                     for ring in poly if len(ring) >= 3]
            items.append((rings, kind))          # with holes
    return items, mapping

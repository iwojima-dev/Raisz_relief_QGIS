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
sheet.py -- sheet decoration: frames (including the checkered map border
with degree fractions), graticule ticks with labels, an old-style scale
bar, auto legend. Drawn in the existing axes in data coordinates
(raster pixels); the 4% margin zone is reserved by the cores.

z=3.5 (below framework 4 and strokes 5): relief displaced upward
overlaps the top frame. Cartouches (scale bar, compass) are z=20+, on top.

Coordinate labels: always D°MM′ (WGS84, hemispheres N/S/E/W); the grid step
is 15 minutes or coarser, so seconds are never written. Any CRS converts
via pyproj. Works with a rotated canvas (geff is a true affine transform).
"""

from __future__ import annotations

import numpy as np

_PXI = 90.0   # data px per figure inch (figsize = cols/90 in all cores)
_Z = 3.5      # frame/ticks: below framework (4) and strokes (5) -- relief
              # line work displaced upward overlaps the frame; the relief
              # BODY (draped fill, z~1) does not, so the top horizontal
              # frame lines are additionally BROKEN along the silhouette
              # (top_profile); above dot screen (1.6) and stipple (3)
_ZC = 20.0    # cartouches (scale bar, legend): on top of everything
_TOL = 0.75   # silhouette tolerance, px: relief flush with a line keeps it

# grid step candidates, arc-seconds (15 minutes or coarser)
_STEPS_SEC = [900, 1800, 3600, 7200, 18000, 36000, 72000]


def _pt(px, cols, margin):
    """Data px -> points (line widths, label font size)."""
    return 72.0 * (cols / _PXI) / (cols + 2.0 * margin) * px


def settle_style(rows, cols, scale=1.0, base_size=16.0):
    """Settlement marker and label sizes tied to the SHEET, not to points.

    The label font size used to be a constant (theme: label_size=9), while
    all sheet decoration is sized as a fraction of the margin via _pt().
    Points-per-data-pixel do not depend on scene size (~0.74), so coordinate
    labels grow with the canvas but place names do not: on a scene twice as
    wide the lag is already threefold. Here the base is also a fraction of
    the margin (0.11*margin) with a 7 pt floor.

    scale -- user multiplier (1.0 = auto). Returns a dict:
      label_size -- label size, points;
      size       -- marker area, points^2 (grows as the square of the side,
                    so the marker/label ratio is preserved);
      label_dx   -- label offset from the marker, data px;
      marker_lw  -- marker edge width, points.
    """
    margin = 0.04 * max(rows, cols)
    px = max(7.0 / _pt(1.0, cols, margin), 0.11 * margin) * float(scale)
    pt = _pt(px, cols, margin)
    k = pt / 9.0                       # 9 pt -- the former fixed size
    return dict(label_size=pt,
                size=float(base_size) * k * k,
                label_dx=max(3.0, 0.30 * px),
                marker_lw=max(0.4, 0.4 * k))


def apply_settle_style(styles, rows, cols, font=None, scale=1.0):
    """Replace the sizes in styles['settle'] with sheet-tied ones. The base
    marker area is taken from the theme so paper and coloured-fill presets
    keep their ratio."""
    st = dict(styles.get("settle", {}))
    st.update(settle_style(rows, cols, scale, st.get("size", 16.0)))
    if font:
        st["label_font"] = font
    out = dict(styles)
    out["settle"] = st
    return out


def _dm(v, is_lat):
    """Decimal degrees -> D°MM′ string with a hemisphere letter.
    Grid step is >= 15′, seconds are always zero -- omitted."""
    hemi = (("N" if v >= 0 else "S") if is_lat
            else ("E" if v >= 0 else "W"))
    a = abs(v)
    d = int(a)
    m = int(round((a - d) * 60.0))
    if m == 60:
        m = 0
        d += 1
    return "%d°%02d′ %s" % (d, m, hemi)


def _lonlat_fn(proj_wkt):
    """Raster CRS -> function (x, y) -> (lon, lat) WGS84."""
    from pyproj import CRS, Transformer
    crs = CRS.from_user_input(proj_wkt)
    if crs.is_geographic:
        return lambda x, y: (np.asarray(x, float), np.asarray(y, float))
    tr = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)
    return lambda x, y: tr.transform(x, y)


def _pix2world(colv, rowv, g):
    x = g[0] + colv * g[1] + rowv * g[2]
    y = g[3] + colv * g[4] + rowv * g[5]
    return x, y


def _top_gaps(y, top_profile, cols):
    """X intervals where the relief silhouette rises ABOVE the horizontal
    line at level y (Y axis points down: "above" = smaller). top_profile
    is the per-column minimum screen Y; its length need not equal cols."""
    if top_profile is None:
        return []
    tp = np.asarray(top_profile, float)
    n = tp.size
    if n < 2:
        return []
    covered = np.isfinite(tp) & (tp <= y - _TOL)
    if not covered.any():
        return []
    sx = float(cols) / n
    m = covered.astype(np.int8)
    d = np.diff(np.concatenate(([0], m, [0])))
    return [(float(i0) * sx, float(i1) * sx)
            for i0, i1 in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1))]


def _hline_segs(y, xa, xb, top_profile, cols):
    """Horizontal line at level y from xa to xb, broken by the silhouette."""
    segs = []
    x = xa
    for ga, gb in _top_gaps(y, top_profile, cols):
        ga = max(ga, xa); gb = min(gb, xb)
        if gb <= ga:
            continue
        if ga > x:
            segs.append([(x, y), (ga, y)])
        x = max(x, gb)
    if x < xb:
        segs.append([(x, y), (xb, y)])
    return segs


def _covered_at(top_profile, cols, x, y):
    """Does the relief silhouette cover the point (x, y)?"""
    if top_profile is None:
        return False
    tp = np.asarray(top_profile, float)
    if tp.size < 1:
        return False
    i = int(np.clip(round(x * tp.size / float(cols)), 0, tp.size - 1))
    return bool(np.isfinite(tp[i]) and tp[i] <= y - _TOL)


def _rect(ax, x0, y0, x1, y1, lw_pt, color, top_profile=None, cols=None):
    """Frame. With top_profile given, the TOP side (y0) is drawn as
    segments -- no line where the relief juts past the top edge."""
    if top_profile is None:
        from matplotlib.patches import Rectangle
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False,
                               edgecolor=color, linewidth=lw_pt,
                               joinstyle="miter", zorder=_Z, clip_on=False))
        return
    from matplotlib.collections import LineCollection
    segs = [[(x0, y1), (x1, y1)],            # bottom
            [(x0, y0), (x0, y1)],            # left
            [(x1, y0), (x1, y1)]]            # right
    segs += _hline_segs(y0, x0, x1, top_profile, cols if cols else x1)
    ax.add_collection(LineCollection(
        segs, colors=[color], linewidths=lw_pt, capstyle="butt",
        zorder=_Z, clip_on=False))


def _step_deg(span_deg, n_target=3):
    """Grid step: at most n_target labels per side extent."""
    span_sec = abs(span_deg) * 3600.0
    for st in _STEPS_SEC:
        if span_sec / st <= n_target:
            return st / 3600.0
    return _STEPS_SEC[-1] / 3600.0


def _crossings(tv, vv, target):
    """Parameters t where the curve vv(t) crosses the target level.
    Monotonicity is not required (projection/rotation may break it)."""
    d = vv - target
    out = []
    idx = np.where(np.sign(d[:-1]) * np.sign(d[1:]) <= 0)[0]
    for i in idx:
        if d[i + 1] == d[i]:
            continue
        w = d[i] / (d[i] - d[i + 1])
        if 0.0 <= w <= 1.0:
            out.append(float(tv[i] + (tv[i + 1] - tv[i]) * w))
    return out


def _side_values(geff, f, rows, cols, N=512):
    """Geographic values along the four raster sides.
    Returns (t, sides, vals): sides -- (kind, col(t), row(t), outward
    normal, label style); vals -- lon or lat along the side."""
    t = np.linspace(0.0, 1.0, N)
    zc = np.zeros(N)
    on = np.ones(N)
    sides = [
        ("lon", t * cols, zc, (0.0, -1.0),
         dict(ha="center", va="bottom", rot=0)),
        ("lon", t * cols, on * rows, (0.0, 1.0),
         dict(ha="center", va="top", rot=0)),
        ("lat", zc, t * rows, (-1.0, 0.0),
         dict(ha="center", va="bottom", rot=90)),
        ("lat", on * cols, t * rows, (1.0, 0.0),
         dict(ha="center", va="top", rot=90)),
    ]
    vals = []
    for kind, cv, rv, nrm, st in sides:
        x, y = _pix2world(cv, rv, geff)
        lon, lat = f(x, y)
        vals.append(np.asarray(lon if kind == "lon" else lat, float))
    return t, sides, vals


def _steps(vals):
    step_lon = _step_deg(max(float(np.ptp(vals[0])),
                             float(np.ptp(vals[1])), 1e-9))
    step_lat = _step_deg(max(float(np.ptp(vals[2])),
                             float(np.ptp(vals[3])), 1e-9))
    return step_lon, step_lat


def _checker_frame(ax, geff, f, rows, cols, margin, off, paper, ink,
                   thin, log, top_profile=None):
    """Map border: an inner line along the raster, a gap, and a narrow
    band of alternating black-and-white segments along the outer frame.
    Segment cuts are multiples of 1/5 of the grid step; parity is tied to
    the coordinate value, so checkers agree around the perimeter."""
    from matplotlib.patches import Polygon
    band = 0.22 * off                     # width of the checker band
    r_in = off - band                     # inner edge of the band
    t, sides, vals = _side_values(geff, f, rows, cols)
    step_lon, step_lat = _steps(vals)
    for si_, ((kind, cv, rv, nrm, st), vv) in enumerate(zip(sides, vals)):
        sub = (step_lon if kind == "lon" else step_lat) / 5.0
        k0 = int(np.floor(vv.min() / sub))
        k1 = int(np.ceil(vv.max() / sub))
        cuts = [0.0, 1.0]
        for k in range(k0, k1 + 1):
            cuts.extend(_crossings(t, vv, k * sub))
        cuts = sorted(set(cuts))
        for a, b in zip(cuts[:-1], cuts[1:]):
            if b - a < 1e-6:
                continue
            mid = 0.5 * (a + b)
            v_mid = float(np.interp(mid, t, vv))
            dark = int(np.floor(v_mid / sub)) % 2 == 0
            pa = (float(np.interp(a, t, cv)), float(np.interp(a, t, rv)))
            pb = (float(np.interp(b, t, cv)), float(np.interp(b, t, rv)))
            if si_ == 0 and _covered_at(top_profile, cols,
                                        0.5 * (pa[0] + pb[0]), -r_in):
                continue          # checker hidden by relief jutting out
            ia = (pa[0] + nrm[0] * r_in, pa[1] + nrm[1] * r_in)
            ib = (pb[0] + nrm[0] * r_in, pb[1] + nrm[1] * r_in)
            qa = (pa[0] + nrm[0] * off, pa[1] + nrm[1] * off)
            qb = (pb[0] + nrm[0] * off, pb[1] + nrm[1] * off)
            ax.add_patch(Polygon(
                [ia, ib, qb, qa], closed=True,
                facecolor=(ink if dark else paper), edgecolor=ink,
                linewidth=thin * 0.5, zorder=_Z, clip_on=False))
    _rect(ax, 0, 0, cols, rows, thin, ink, top_profile, cols)
    _rect(ax, -r_in, -r_in, cols + r_in, rows + r_in, thin * 0.8, ink,
          top_profile, cols)
    _rect(ax, -off, -off, cols + off, rows + off, thin, ink,
          top_profile, cols)


def _north_vec(geff, proj_wkt, rows, cols):
    """Unit vector toward true north in data coordinates
    (pixels). Works on any projection and with a rotated canvas:
    sheet center -> WGS84 -> a point slightly north -> back to CRS ->
    inverse affine to pixels."""
    from pyproj import CRS, Transformer
    crs = CRS.from_user_input(proj_wkt)
    c, r = cols / 2.0, rows / 2.0
    x0, y0 = _pix2world(c, r, geff)
    if crs.is_geographic:
        lon, lat = float(x0), float(y0)
        x1, y1 = lon, lat + 0.01
    else:
        fwd = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)
        inv = Transformer.from_crs(CRS.from_epsg(4326), crs, always_xy=True)
        lon, lat = fwd.transform(x0, y0)
        x1, y1 = inv.transform(lon, lat + 0.01)
    g = geff
    det = g[1] * g[5] - g[2] * g[4]
    dx, dy = x1 - x0, y1 - y0
    dc = (g[5] * dx - g[2] * dy) / det
    dr = (-g[4] * dx + g[1] * dy) / det
    n = float(np.hypot(dc, dr))
    return (dc / n, dr / n) if n > 0 else (0.0, -1.0)


def _compass(ax, geff, proj_wkt, rows, cols, margin, paper, ink,
             style, fs_px, log):
    """North arrow (style=1) or an 8-point compass rose (style=2).
    A cartouche in the upper-right corner, oriented to true north."""
    from matplotlib.patches import Polygon
    try:
        nc, nr = _north_vec(geff, proj_wkt, rows, cols)
    except Exception as e:
        if log:
            log("Compass: north assumed up (CRS/pyproj: %s)" % e)
        nc, nr = 0.0, -1.0
    th0 = np.arctan2(nr, nc)              # north angle in the data plane
    L = 0.75 * margin                     # main ray length (v7.2.4: halved)
    cx = cols - 1.4 * margin - L
    cy = 1.4 * margin + L
    lwp = _pt(max(0.8, 0.010 * margin), cols, margin)

    def ray(theta, length):
        tip = (cx + length * np.cos(theta), cy + length * np.sin(theta))
        for sgn, fc in ((1.0, ink), (-1.0, paper)):
            phi = theta + sgn * np.pi / 8.0
            mid = (cx + 0.34 * length * np.cos(phi),
                   cy + 0.34 * length * np.sin(phi))
            ax.add_patch(Polygon([(cx, cy), tip, mid], closed=True,
                                 facecolor=fc, edgecolor=ink,
                                 linewidth=lwp, zorder=_ZC, clip_on=False))

    if style == 2:
        for i in (1, 3, 5, 7):            # diagonal rays: shorter, underneath
            ray(th0 + i * np.pi / 4.0, 0.62 * L)
        for i in (2, 4, 6):               # E, S, W
            ray(th0 + i * np.pi / 4.0, L)
        ray(th0, L)                       # north ray on top
    else:
        ray(th0, L)                       # single north arrow
    fs = _pt(max(0.5 * fs_px, 0.11 * margin), cols, margin)
    ax.text(cx + 1.28 * L * np.cos(th0), cy + 1.28 * L * np.sin(th0), "N",
            fontsize=fs, color=ink, ha="center", va="center",
            fontweight="bold", zorder=_ZC, clip_on=False)


def _haversine_m(lon1, lat1, lon2, lat2):
    R = 6371008.8
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2.0 * R * np.arcsin(np.sqrt(a))


def _meters_per_px(geff, f, rows, cols):
    """Meters per pixel horizontally at the sheet center (via WGS84 --
    works with any CRS)."""
    c, r = cols / 2.0, rows / 2.0
    x0, y0 = _pix2world(np.array([c]), np.array([r]), geff)
    x1, y1 = _pix2world(np.array([c + 1.0]), np.array([r]), geff)
    lo0, la0 = f(x0, y0)
    lo1, la1 = f(x1, y1)
    return float(_haversine_m(lo0[0], la0[0], lo1[0], la1[0]))


def _nice_len_m(target_m):
    """Round to a nice length of 1/2/2.5/5 x 10^n meters."""
    if target_m <= 0:
        return 1.0
    mag = 10.0 ** np.floor(np.log10(target_m))
    for c in (5.0, 2.5, 2.0, 1.0):
        if c * mag <= target_m:
            return c * mag
    return mag


def _fmt_km(m):
    return ("%g km" % (m / 1000.0)) if m >= 1000.0 else ("%g m" % m)


def _scalebar(ax, geff, f, rows, cols, margin, paper, ink, fs_px, log):
    """Old-style scale bar: 4 alternating black-and-white segments,
    labels at 0 / midpoint / full length. Lower-left corner."""
    from matplotlib.patches import Rectangle
    try:
        mpp = _meters_per_px(geff, f, rows, cols)
    except Exception as e:
        if log:
            log("Scale bar skipped: %s" % e)
        return
    total_m = _nice_len_m(0.11 * cols * mpp)   # v7.2.4: halved
    L = total_m / mpp                     # bar length, data px
    seg = L / 4.0
    fs_bar = 0.5 * fs_px                  # v7.2.4: labels halved
    h = max(2.0, 0.9 * fs_bar)            # bar height
    x0 = 1.2 * margin
    y1 = rows - 1.2 * margin              # bar bottom
    y0 = y1 - h
    fs = _pt(fs_bar, cols, margin)
    lwp = _pt(max(1.0, 0.10 * h), cols, margin)
    for i in range(4):
        ax.add_patch(Rectangle(
            (x0 + i * seg, y0), seg, h,
            facecolor=(ink if i % 2 == 0 else paper), edgecolor=ink,
            linewidth=lwp, zorder=_ZC, clip_on=False))
    for frac, m in ((0.0, 0.0), (0.5, total_m / 2.0), (1.0, total_m)):
        txt = "0" if m == 0 else _fmt_km(m)
        ax.text(x0 + frac * L, y0 - 0.5 * h, txt, fontsize=fs, color=ink,
                ha="center", va="bottom", zorder=_ZC, clip_on=False)


def _legend_items(extras):
    """(key, label) list of the layers actually present."""
    ov = extras.get("overlays") or {}
    items = []
    if extras.get("fall"):
        items.append(("fall", "Slope hachures"))
    if extras.get("stipple"):
        items.append(("stipple", "Plains stipple"))
    if ov.get("lake") or ov.get("sea") or extras.get("auto_sea"):
        items.append(("water", "Waters"))
    if ov.get("river"):
        items.append(("river", "Rivers"))
    if ov.get("marsh"):
        items.append(("marsh", "Marshes"))
    if ov.get("road"):
        items.append(("road", "Roads"))
    if ov.get("settle_pt") or ov.get("settle_poly"):
        items.append(("settle", "Settlements"))
    if ov.get("forest"):
        items.append(("forest", "Forest"))
    if ov.get("sand"):
        items.append(("sand", "Sand"))
    if ov.get("ice"):
        items.append(("ice", "Ice"))
    if ov.get("scrub"):
        items.append(("scrub", "Scrub"))
    if ov.get("grass"):
        items.append(("grass", "Grassland"))
    return items[:8]


def _glyph(ax, key, st, x, yc, w, h, ink):
    """Mini layer sample in a cell (x..x+w, center yc). Theme styles."""
    from matplotlib.patches import Rectangle
    from matplotlib.lines import Line2D
    lc = st.get("landcover", {})

    def line(xs, ys, color, lw, **kw):
        ax.add_line(Line2D(xs, ys, color=color, linewidth=lw,
                           zorder=_ZC, clip_on=False, **kw))

    if key == "fall":
        for i, lw in enumerate((2.4, 1.4, 2.0, 1.0)):
            xi = x + w * (0.2 + 0.2 * i)
            line([xi, xi], [yc - h * 0.35, yc + h * 0.35], ink, lw)
    elif key == "stipple":
        for i in range(5):
            ax.plot(x + w * (0.15 + 0.175 * i), yc + h * 0.18 * ((-1) ** i),
                    ".", color=ink, markersize=2.2, zorder=_ZC, clip_on=False)
    elif key == "water":
        s = st.get("lake", {})
        ax.add_patch(Rectangle((x + w * 0.1, yc - h * 0.3), w * 0.8, h * 0.6,
                               facecolor=s.get("face", ink),
                               edgecolor=s.get("edge", ink), linewidth=0.7,
                               zorder=_ZC, clip_on=False))
    elif key == "river":
        s = st.get("river", {})
        xs = np.linspace(x + w * 0.1, x + w * 0.9, 24)
        ys = yc + h * 0.2 * np.sin(np.linspace(0, 3 * np.pi, 24))
        line(xs, ys, s.get("color", ink), 1.0)
    elif key == "marsh":
        s = st.get("marsh", {})
        for i in range(3):
            yy = yc - h * 0.25 + i * h * 0.25
            line([x + w * 0.15, x + w * 0.55], [yy, yy],
                 s.get("edge", ink), 0.7)
            line([x + w * 0.62, x + w * 0.88], [yy, yy],
                 s.get("edge", ink), 0.7)
    elif key == "road":
        s = st.get("road", {})
        line([x + w * 0.1, x + w * 0.9], [yc, yc],
             s.get("casing", "#fff"), s.get("casing_lw", 1.8))
        line([x + w * 0.1, x + w * 0.9], [yc, yc],
             s.get("core", ink), s.get("core_lw", 0.7))
    elif key == "settle":
        s = st.get("settle", {})
        ax.plot(x + w * 0.5, yc, "o", color=s.get("color", ink),
                markersize=3.2, zorder=_ZC, clip_on=False)
    elif key == "forest":
        s = lc.get("forest", {})
        for dx, dy in ((0.25, 0.15), (0.5, -0.2), (0.75, 0.15)):
            ax.plot(x + w * dx, yc + h * dy, "o", color=s.get("color", ink),
                    markersize=2.6, alpha=s.get("alpha", 0.8),
                    zorder=_ZC, clip_on=False)
    else:   # sand / ice / scrub / grass -- dot-and-dash cover glyphs
        s = lc.get(key, {})
        for i in range(4):
            xi = x + w * (0.18 + 0.21 * i)
            line([xi, xi + w * 0.08], [yc + h * 0.12 * ((-1) ** i)] * 2,
                 s.get("color", ink), s.get("lw", 0.6))


def _legend(ax, rows, cols, margin, paper, ink, fs_px, extras, log):
    """Legend key: a cartouche in the lower-right corner, only the layers
    actually present, samples in the current theme styles."""
    from matplotlib.patches import Rectangle
    items = _legend_items(extras)
    if not items:
        return
    st = extras.get("styles") or {}
    fs_leg_px = 0.85 * fs_px
    fs = _pt(fs_leg_px, cols, margin)
    row_h = 1.9 * fs_leg_px
    gl_w = 4.0 * fs_leg_px
    txt_w = 0.60 * fs_leg_px * max(len(lbl) for _, lbl in items)
    pad = 0.9 * fs_leg_px
    W = gl_w + txt_w + 3 * pad
    H = row_h * len(items) + 2 * pad
    x0 = cols - 1.2 * margin - W
    y0 = rows - 1.2 * margin - H
    ax.add_patch(Rectangle((x0, y0), W, H, facecolor=paper, alpha=0.92,
                           edgecolor=ink,
                           linewidth=_pt(max(1.2, 0.02 * margin), cols, margin),
                           zorder=_ZC - 0.5, clip_on=False))
    for i, (key, lbl) in enumerate(items):
        yc = y0 + pad + row_h * (i + 0.5)
        _glyph(ax, key, st, x0 + pad, yc, gl_w, row_h * 0.8, ink)
        ax.text(x0 + 2 * pad + gl_w, yc, lbl, fontsize=fs, color=ink,
                ha="left", va="center", zorder=_ZC, clip_on=False)


def _draw_ticks(ax, geff, f, rows, cols, margin, ink, off, fs_px, log,
                top_profile=None):
    """Graticule ticks: outward from the outer frame edge; labels are
    offset from the frame (from its outer line for double/map border)."""
    from matplotlib.collections import LineCollection
    fs = _pt(fs_px, cols, margin)
    lw = _pt(max(1.2, 0.02 * margin), cols, margin)
    tlen = 0.20 * margin
    toff = off + tlen + 0.16 * margin     # label anchor with a gap
    t, sides, vals = _side_values(geff, f, rows, cols)
    step_lon, step_lat = _steps(vals)
    segs = []
    n = 0
    for si_, ((kind, cv, rv, nrm, st), vv) in enumerate(zip(sides, vals)):
        step = step_lon if kind == "lon" else step_lat
        side_len = cols if kind == "lon" else rows
        cand = []
        for k in range(int(np.ceil(vv.min() / step)),
                       int(np.floor(vv.max() / step)) + 1):
            for tc in _crossings(t, vv, k * step):
                cand.append((tc, k * step))
        cand.sort()
        if len(cand) > 3:   # at most three labels: ends + middle
            cand = [cand[0], cand[len(cand) // 2], cand[-1]]
        kept = []           # label overlap control along the side
        for tc, target in cand:
            txt = _dm(target, kind == "lat")
            w_px = 0.62 * fs_px * len(txt)
            pos = tc * side_len
            if kept and (pos - kept[-1][0]) < 0.58 * (w_px + kept[-1][1]):
                continue
            kept.append((pos, w_px, tc, txt))
        for pos, w_px, tc, txt in kept:
            pc = float(np.interp(tc, t, cv))
            pr = float(np.interp(tc, t, rv))
            if si_ == 0 and _covered_at(top_profile, cols, pc, -off):
                continue      # tick and label hidden by the relief
            segs.append([(pc + nrm[0] * off, pr + nrm[1] * off),
                         (pc + nrm[0] * (off + tlen),
                          pr + nrm[1] * (off + tlen))])
            ax.text(pc + nrm[0] * toff, pr + nrm[1] * toff, txt,
                    fontsize=fs, color=ink, zorder=_Z, clip_on=False,
                    ha=st["ha"], va=st["va"], rotation=st["rot"],
                    rotation_mode="anchor")
            n += 1
    if segs:
        ax.add_collection(LineCollection(
            segs, colors=[ink], linewidths=lw, zorder=_Z, clip_on=False))
    return n


def draw_sheet(ax, geff, proj_wkt, rows, cols, margin, paper, ink, opts,
               top_pad=0.0, extras=None, log=None, top_profile=None):
    """Sheet decoration. opts: dict(frame=0..4, ticks, scalebar, legend,
    grain, dot, misreg). frame: 0 none, 1 single, 2 double,
    3 thick-thin, 4 map border (checkered degree fractions).
    misreg is applied by the core after savefig (print_fx.misregister).

    top_profile -- per-column minimum screen Y of the relief (data px,
    axis down): the top horizontal frame lines, checkers and ticks are
    broken wherever the relief juts past the top edge of the sheet."""
    extras = extras or {}
    frame = int(opts.get("frame", 0))
    thin = _pt(max(1.5, 0.022 * margin), cols, margin)
    thick = _pt(max(3.0, 0.065 * margin), cols, margin)
    off = 0.55 * margin if frame in (2, 3, 4) else 0.0
    fs_px = max(7.0 / _pt(1.0, cols, margin), 0.18 * margin)
    f = None
    if frame == 4 or opts.get("ticks") or opts.get("scalebar"):
        try:
            f = _lonlat_fn(proj_wkt)
        except Exception as e:
            if log:
                log("CRS/pyproj unavailable, graticule and scale bar skipped: %s" % e)
    if frame == 1:
        _rect(ax, 0, 0, cols, rows, thick * 0.7, ink, top_profile, cols)
    elif frame == 2:
        _rect(ax, 0, 0, cols, rows, thin, ink, top_profile, cols)
        _rect(ax, -off, -off, cols + off, rows + off, thin, ink,
              top_profile, cols)
    elif frame == 3:
        _rect(ax, 0, 0, cols, rows, thin, ink, top_profile, cols)
        _rect(ax, -off, -off, cols + off, rows + off, thick, ink,
              top_profile, cols)
    elif frame == 4:
        if f is not None:
            _checker_frame(ax, geff, f, rows, cols, margin, off,
                           paper, ink, thin, log, top_profile)
        else:   # fallback without CRS: double frame
            _rect(ax, 0, 0, cols, rows, thin, ink, top_profile, cols)
            _rect(ax, -off, -off, cols + off, rows + off, thin, ink,
                  top_profile, cols)
    n = 0
    if opts.get("ticks") and f is not None:
        n = _draw_ticks(ax, geff, f, rows, cols, margin, ink, off,
                        fs_px, log, top_profile)
    if opts.get("scalebar") and f is not None:
        _scalebar(ax, geff, f, rows, cols, margin, paper, ink, fs_px, log)
    if int(opts.get("compass", 0)) > 0:
        _compass(ax, geff, proj_wkt, rows, cols, margin, paper, ink,
                 int(opts["compass"]), fs_px, log)
    if opts.get("legend"):
        _legend(ax, rows, cols, margin, paper, ink, fs_px, extras, log)
    if opts.get("grain") or opts.get("dot"):
        from . import print_fx
        if opts.get("grain"):
            print_fx.draw_grain(ax, -margin, cols + margin,
                                -top_pad - margin, rows + margin, ink)
        if opts.get("dot"):
            print_fx.draw_dotscreen(ax, rows, cols, ink)
    return dict(sheet_ticks=n)

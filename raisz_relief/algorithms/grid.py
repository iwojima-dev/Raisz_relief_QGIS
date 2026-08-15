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
grid.py -- the single working grid of the project.

Both the core (hachure computation) and vector overlay/rasterization
must rely on ONE AND THE SAME pixel grid, or the fill and the line work
drift apart. So the grid definition lives here: the algorithm calls
working_grid() once and hands the result to every consumer.

Dependencies: numpy, gdal, scipy.
"""

from __future__ import annotations

import numpy as np
from osgeo import gdal
from scipy import ndimage


class Grid:
    """Description of the working raster grid and its georeference."""

    def __init__(self, ox, oy, nx, ny, gt, geff, scale, proj):
        self.ox, self.oy = ox, oy          # source DEM size, px
        self.nx, self.ny = nx, ny          # working size, px
        self.gt = gt                       # source GeoTransform
        self.geff = geff                   # effective GT of the working grid
        self.scale = scale                 # downsampling factor (>=1)
        self.proj = proj                   # projection WKT

    @property
    def extent(self):
        """(xmin, ymin, xmax, ymax) in map coordinates, from the source data."""
        x0, y0 = self.gt[0], self.gt[3]
        x1 = x0 + self.gt[1] * self.ox
        y1 = y0 + self.gt[5] * self.oy
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    @property
    def affine(self):
        """affine.Affine of the working grid (for rasterio)."""
        from affine import Affine
        g = self.geff
        return Affine(g[1], g[2], g[0], g[4], g[5], g[3])


def world_to_pixel(xy, geff):
    """(N,2) map -> (N,2) pixels (col, row) via the effective georeference.
    Full affine inversion: supports a rotated geff (b,d terms != 0)."""
    xy = np.asarray(xy, dtype="float64")
    g0, g1, g2, g3, g4, g5 = geff
    dx = xy[:, 0] - g0
    dy = xy[:, 1] - g3
    det = g1 * g5 - g2 * g4
    col = (g5 * dx - g2 * dy) / det
    row = (-g4 * dx + g1 * dy) / det
    return np.column_stack([col, row])


def rotate_view(z, geff, k):
    """Rotate the working array and georeference by k*90° (k=0..3) to
    change the view point. Returns (z_rot, geff_rot); geff_rot may carry
    rotation terms (b,d) understood by the full-affine world_to_pixel.
    The source geff is assumed axis-aligned (b=d=0)."""
    k = int(k) % 4
    if k == 0:
        return z, geff
    R, C = z.shape
    ox, px, _, oy, _, py = geff
    zr = np.rot90(z, k)
    if k == 1:
        geff_rot = (ox + px * C, 0.0, -px, oy, py, 0.0)
    elif k == 2:
        geff_rot = (ox + px * C, -px, 0.0, oy + py * R, 0.0, -py)
    else:  # k == 3
        geff_rot = (ox, 0.0, px, oy + py * R, -py, 0.0)
    return zr, geff_rot


def working_grid(dem_path, max_px=None):
    """Define the working grid. max_px=None -> full resolution (classic)."""
    ds = gdal.Open(dem_path)
    if ds is None:
        raise RuntimeError("Cannot open the DEM: " + str(dem_path))
    ox, oy = ds.RasterXSize, ds.RasterYSize
    gt = ds.GetGeoTransform()
    proj = ds.GetProjection()
    if max_px and max(ox, oy) > max_px:
        scale = max(ox, oy) / float(max_px)
    else:
        scale = 1.0
    nx = max(1, int(round(ox / scale)))
    ny = max(1, int(round(oy / scale)))
    geff = (gt[0], gt[1] * ox / float(nx), 0.0,
            gt[3], 0.0, gt[5] * oy / float(ny))
    ds = None
    return Grid(ox, oy, nx, ny, gt, geff, scale, proj)


def rel_scale_k(disp, ny, target_pct, vert_exag=1.0, log=None):
    """Displacement normalization factor: p99(disp) > 0 is stretched to
    target_pct % of the sheet height (ny rows). vert_exag acts as a
    multiplier on top of the target (1.0 = exactly the target). p99
    instead of max keeps single spikes (masts, DEM artifacts) from
    dominating. Returns the scalar k (disp *= k)."""
    pos = disp[disp > 1e-9]
    p99 = float(np.percentile(pos, 99)) if pos.size else 0.0
    if p99 <= 1e-9:
        if log:
            log("Relative scale: relief has no expression (p99~0), "
                "normalization skipped")
        return 1.0
    k = (target_pct / 100.0) * float(ny) * float(vert_exag) / p99
    if log:
        log("Relative scale: p99(disp)=%.1f px, target %.1f%% of height "
            "x exaggeration %.2f, k=%.3f (result %.0f px)"
            % (p99, target_pct, vert_exag, k, p99 * k))
    return k


def rel_interval(zmin, zmax, n_levels, log=None):
    """Relative contour interval: (zmax-zmin)/N belts instead of absolute
    meters. Affects both the framework and the fall-line length (a stroke
    ends after descending one interval)."""
    n = max(int(round(n_levels)), 2)
    iv = max((float(zmax) - float(zmin)) / n, 1e-6)
    if log:
        log("Relative interval: range %.0f m / %d belts = %.1f m"
            % (zmax - zmin, n, iv))
    return iv


def rel_interval_local(relief, n_levels, p_hi=90.0, log=None):
    """Contour step from the LOCAL (amplified) relief instead of the full
    elevation range. Takes the p_hi percentile of relief>0 as the "typical
    landform" and divides by the number of belts, so belts densely cut the
    FORMS THEMSELVES rather than the regional trend. The old global
    (zmax-zmin)/N inflated the interval when the trend was large and local
    relief small, giving long stretched strokes."""
    a = np.asarray(relief, dtype="float64")
    pos = a[a > 1e-6]
    span = float(np.percentile(pos, p_hi)) if pos.size else 0.0
    n = max(int(round(n_levels)), 2)
    iv = max(span / n, 1e-6)
    if log:
        log("Local rel. interval: p%.0f(relief)=%.1f m / %d belts = %.1f m"
            % (p_hi, span, n, iv))
    return iv


def rel_slope_norm(slope_deg, p_cut=30.0, p_top=95.0, log=None):
    """Percentile normalization of scene slopes (the "relative slopes"
    flag). Returns (threshold, norm): the stroke cutoff threshold is the
    p_cut percentile of non-zero slopes, the full graphic range is p_top
    (instead of the fixed 4 deg / 45 deg). The price is losing
    cross-sheet comparability of stroke weight between scenes."""
    s = slope_deg[slope_deg > 0.05]
    if s.size == 0:
        return 0.0, 45.0
    thr = float(np.percentile(s, p_cut))
    top = float(np.percentile(s, p_top))
    top = max(top, thr * 1.5, 1e-3)
    if log:
        log("Relative slopes: threshold p%.0f=%.2f deg, norm p%.0f=%.2f deg "
            "(instead of absolute degrees)" % (p_cut, thr, p_top, top))
    return thr, top


def steep_weight(z, px, py, base_scale_px=55, sigma_fine=2.0,
                 sigma_broad=None, w_min=0.12, p_ref=95.0, log=None):
    """"What to lift" selector for the relative mode: weight w in
    [w_min, 1] by the SHARPNESS OF SMALL FORMS, not by height.

    Takes a scale band (residual = smoothed-from-noise minus
    smoothed-from-broad-forms) and measures its steepness:
      * small steep forms (scarps, coastal cliffs) -> w~1 (full lift);
      * plains, broad gentle hills, regional trend -> w~w_min (a little);
      * pixel DEM noise is removed by the narrow sigma_fine smoothing, so
        it is NOT counted as "steep" and is not lifted (fixes noise lift
        on the classic host, which has no Hammond plain suppression).

    w_min>0 means gentle terrain lifts slightly, not to zero. sigma_broad
    sets the upper band edge: forms wider than ~sigma_broad go into the
    "broad" part and are not amplified; default = base_scale_px."""
    if sigma_broad is None:
        sigma_broad = max(float(base_scale_px), 4.0)
    sf = max(float(sigma_fine), 0.5)
    z_fine = ndimage.gaussian_filter(z, sigma=sf)
    z_broad = ndimage.gaussian_filter(z, sigma=float(sigma_broad))
    residual = z_fine - z_broad
    gN, gE = np.gradient(residual, py, px)
    sharp = np.hypot(gE, gN)                       # residual steepness, m/m
    pos = sharp[sharp > 1e-9]
    ref = float(np.percentile(pos, p_ref)) if pos.size else 0.0
    if ref <= 1e-9:
        w = np.full(z.shape, w_min, dtype="float64")
    else:
        wn = np.clip(sharp / ref, 0.0, 1.0)
        w = w_min + (1.0 - w_min) * wn
    if log:
        log("Steepness selector: band sigma=[%.1f,%.1f]px, "
            "p%.0f(sharpness)=%.4f, w in [%.2f,1]"
            % (sf, float(sigma_broad), p_ref, ref, w_min))
    return w


def valid_mask(z, nd):
    """Mask of valid cells. Average resampling blends nodata with data and
    yields "almost nodata" (absurd magnitudes for -3.4e38), so besides the
    exact comparison we also reject out-of-range values."""
    bad = ~np.isfinite(z)
    if nd is not None:
        bad |= (z == nd)
        if abs(nd) > 1e30:
            bad |= (z < -1e30) if nd < 0 else (z > 1e30)
    return ~bad


def _fill_nearest(z, valid):
    """Plug invalid cells with the nearest valid value: needed so that
    gradients and morphology do not fall apart along the edge."""
    if valid.all():
        return z
    zz = np.where(valid, z, np.nan)
    idx = ndimage.distance_transform_edt(
        ~np.isfinite(zz), return_distances=False, return_indices=True)
    return zz[tuple(idx)]


def read_dem(dem_path, grid, nodata_mode="plain", sea_level=0.0):
    """Read the DEM on the working grid. Returns (z, px, py, valid).

    nodata_mode -- what to put in areas without data:
      'plain' -- the nearest valid value (as before): reads as a plain;
      'sea'   -- sea level: flat water, the core adds it to the sea polygons;
      'paper' -- also nearest (for numerical stability), but valid=False and
                 the core draws no fill, no strokes and no framework there.
    """
    ds = gdal.Open(dem_path)
    band = ds.GetRasterBand(1)
    nd = band.GetNoDataValue()
    try:
        z = band.ReadAsArray(buf_xsize=grid.nx, buf_ysize=grid.ny,
                             resample_alg=gdal.GRIORA_Average).astype("float64")
    except Exception:
        z = band.ReadAsArray(buf_xsize=grid.nx, buf_ysize=grid.ny).astype("float64")
    px = abs(grid.geff[1]); py = abs(grid.geff[5])
    valid = valid_mask(z, nd)
    if nodata_mode == "sea":
        z = np.where(valid, z, float(sea_level))
    else:
        z = _fill_nearest(z, valid)
    ds = None
    return z, px, py, valid


def estimate_memory_gb(grid, dpi, n_arrays=12):
    """Rough peak-memory estimate: working arrays + the mpl raster canvas.

    Since 7.4.0 the flow-convergence map is one of the arrays (11 -> 12).
    With valley_break=0 it is never built, but the estimate takes the worst
    case: the memory guard has to fire before the run, not after."""
    cells = grid.nx * grid.ny
    arrays = cells * 8 * n_arrays
    canvas = (grid.nx / 90.0 * dpi) * (grid.ny / 90.0 * dpi) * 4
    return (arrays + canvas) / (1024 ** 3)


def _orient(ring, ccw=True):
    """Orient a ring: ccw=True -- counter-clockwise (exterior),
    ccw=False -- clockwise (hole). Needed so matplotlib cuts out islands."""
    x = ring[:, 0]; y = ring[:, 1]
    area = float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))
    if (area > 0) != ccw:
        return ring[::-1]
    return ring


def sea_polygons(z, geff, level=0.0, min_cells=8):
    """Water polygons from the DEM: connected regions of z <= level.
    Returns a list of polygons, each a list of rings [exterior, hole1, ...]
    (Nx2, map coordinates). Holes = islands/land inside water so they do
    NOT drown. geff may be rotated (full affine). Tiny specks are dropped."""
    from rasterio.features import shapes
    from affine import Affine
    mask = np.asarray(z <= level)
    if not mask.any():
        return []
    aff = Affine.from_gdal(*geff)
    px_area = abs(geff[1] * geff[5] - geff[2] * geff[4])
    out = []
    for geom, val in shapes(mask.astype("uint8"), mask=mask, transform=aff):
        if not val:
            continue
        coords = geom.get("coordinates") or []
        if not coords:
            continue
        ext = np.asarray(coords[0], dtype="float64")
        if len(ext) < 4:
            continue
        mn = ext.min(axis=0); mx = ext.max(axis=0)
        if (mx[0] - mn[0]) * (mx[1] - mn[1]) < min_cells * px_area:
            continue
        rings = [_orient(ext, ccw=True)]
        for h in coords[1:]:                      # holes = islands
            hr = np.asarray(h, dtype="float64")
            if len(hr) >= 4:
                rings.append(_orient(hr, ccw=False))
        out.append(rings)
    return out


def read_dem_window(dem_path, grid, r0, r1, nodata_mode="plain",
                    sea_level=0.0):
    """Read a STRIP of working rows [r0, r1) of the grid (for striping --
    no full DEM array in memory). Returns (z, valid) of shape
    (r1-r0, grid.nx). nodata_mode is as in read_dem."""
    r0 = max(0, int(r0)); r1 = min(int(r1), grid.ny)
    h = r1 - r0
    if h <= 0:
        return np.empty((0, grid.nx)), np.empty((0, grid.nx), bool)
    ds = gdal.Open(dem_path)
    band = ds.GetRasterBand(1)
    nd = band.GetNoDataValue()
    ry0 = int(round(r0 * grid.oy / float(grid.ny)))
    ry1 = int(round(r1 * grid.oy / float(grid.ny)))
    ry1 = min(max(ry1, ry0 + 1), grid.oy)
    try:
        z = band.ReadAsArray(0, ry0, grid.ox, ry1 - ry0,
                             buf_xsize=grid.nx, buf_ysize=h,
                             resample_alg=gdal.GRIORA_Average).astype("float64")
    except Exception:
        z = band.ReadAsArray(0, ry0, grid.ox, ry1 - ry0,
                             buf_xsize=grid.nx, buf_ysize=h).astype("float64")
    valid = valid_mask(z, nd)
    if nodata_mode == "sea":
        z = np.where(valid, z, float(sea_level))
    else:
        z = _fill_nearest(z, valid)
    ds = None
    return z, valid


def nodata_polygons(valid, geff):
    """Polygons of the area WITHOUT data (for nodata='sea'): the same
    rings-with-holes as auto-sea, drawn with the sea style."""
    if valid is None or valid.all():
        return []
    synth = np.where(valid, 1.0, -1.0)
    return sea_polygons(synth, geff, level=0.0, min_cells=1)


def hidden_polygons(vis, geff, min_cells=64):
    """Rings of the INVISIBLE zones (occluded behind displaced ridges),
    built the same +-1 array / zero-level contour way as nodata_polygons,
    so visible islets inside an occluded area come straight through as
    holes. Used to clip area waters that hide behind mountains."""
    if vis is None or vis.all():
        return []
    synth = np.where(vis, 1.0, -1.0)
    return sea_polygons(synth, geff, level=0.0, min_cells=min_cells)


def as_rings(item):
    """Normalise an overlay item to a list of rings [outer, hole1, ...].

    Accepts both a "flat" ring (N,2) and a ready list of rings -- this
    keeps backward compatibility with the old overlay format and lets all
    consumers (compose, patterns) work uniformly, with holes."""
    if isinstance(item, np.ndarray) and item.ndim == 2:
        return [item]
    try:
        first = item[0]
    except Exception:
        return []
    fa = np.asarray(first, dtype="float64")
    if fa.ndim == 2 and fa.shape[-1] == 2:            # already a ring list
        return [np.asarray(r, dtype="float64") for r in item]
    return [np.asarray(item, dtype="float64")]        # a single ring


def flow_convergence(dzdE, dzdN, px, py, sigma=1.5, min_grad=1e-6):
    """Convergence of flow lines: conv = -div(t), where t is the UNIT fall
    vector -- the very direction trace_fall steps along.

    This is a direct measure of two neighbouring strokes being about to
    merge, not an indirect "valley indicator". The divergence of a unit
    field is the reciprocal of the convergence radius: conv = 1/R, where R
    is the distance in METRES over which two adjacent flow lines meet.
    Hence a threshold with physical meaning: break the stroke where R falls
    below the stroke spacing, i.e. exactly where a blot would build up.

    conv > 0 -- convergence (thalweg, concave foot, cirque floor);
    conv < 0 -- divergence (crest, convex nose of a spur).

    Units are 1/m rather than 1/px on purpose: the value does not depend on
    grid resolution, so one threshold serves both the full pass and the
    downsampled one used by strip tiling.

    sigma smooths the DIRECTION before differentiating: the raw derivative
    of a unit vector turns DEM noise into wild spikes. Components are
    smoothed, not the result, so the noise is not amplified.
    """
    g = np.hypot(dzdE, dzdN)
    np.maximum(g, 1e-12, out=g)
    # components in (row, column) order -- same as the step in trace_fall:
    # dr = +dzdN, dc = -dzdE
    t_r = dzdN / g
    t_c = -dzdE / g
    if sigma and sigma > 0:
        ndimage.gaussian_filter(t_r, sigma=float(sigma), output=t_r)
        ndimage.gaussian_filter(t_c, sigma=float(sigma), output=t_c)
    conv = np.gradient(t_r, float(py), axis=0)
    del t_r
    conv += np.gradient(t_c, float(px), axis=1)
    del t_c
    np.negative(conv, out=conv)
    # on horizontal flats the fall direction is undefined and the
    # divergence there is pure noise -- suppress it
    conv[g < min_grad] = 0.0
    return conv


def convergence_threshold(fall_spacing, px, py, strength):
    """Convergence threshold for breaking a stroke, 1/m. The convergence
    radius is compared with the stroke spacing: at strength=1 the stroke
    breaks where adjacent flow lines meet within one fall_spacing (exactly
    where strokes fuse into a blot); a lower strength pushes the threshold
    out, demanding sharper convergence.

    Returns np.inf for strength<=0 -- breaking disabled.
    """
    s = float(strength)
    if s <= 0.0:
        return np.inf
    mpp = (float(px) + float(py)) / 2.0
    r_thr = max(float(fall_spacing), 0.5) * mpp / min(s, 1.0)
    return 1.0 / max(r_thr, 1e-6)


def drop_fraction(slope_n, strength, expo=0.6, min_frac=0.12):
    """Fraction of the contour interval a stroke descends before breaking.

    Fall-line length is governed NOT by a cap on the number of steps but by
    the break after descending one interval. Capping the step count barely
    works: the cap grows with slope while the actual length falls, the two
    cross at about 7 degrees, and above 8 the cap never bites at all. Below
    4 degrees there are no strokes anyway -- min_slope_deg removes them --
    so the working window came out about a degree and a half wide.

    Applying the coefficient to the descent threshold itself hits the
    mechanism that sets the length, and works across the whole slope range.
    At 5 degrees with strength=0.6 the stroke breaks after descending 22 m
    instead of 40, i.e. half as long; on steep ground the effect is small
    because the interval is reached in 4-7 steps anyway.

    strength=0 restores the previous behaviour (fraction 1.0).
    """
    s = float(np.clip(strength, 0.0, 1.0))
    if s <= 0.0:
        return 1.0
    sn = float(np.clip(slope_n, 0.0, 1.0))
    return max(float(min_frac), (1.0 - s) + s * (sn ** float(expo)))


def bench_spacing_px(slope_deg, interval, mpp):
    """Contour BENCH SPACING in pixels -- the map distance from one contour
    to the next at the given slope. Computed POINTWISE from the slope at the
    seed: wide on gentle ground, narrow on steep, so the filter window
    follows it. Without that, hachuring on gentle swells falls apart into
    separate contours and gets removed wholesale.

    Not derived from the actual stroke length: flat_short shortens that, and
    the window would drift along with the shortening.
    """
    t = np.tan(np.radians(max(float(slope_deg), 0.5)))
    return float(np.clip(interval / max(t * float(mpp), 1e-3), 2.0, 60.0))


def sparse_levels_mask(seeds, levels, bench_px, strength, log=None):
    """Keep-mask for strokes: how many DISTINCT contour levels the hachuring
    around a given stroke describes.

    Two earlier attempts measured the wrong thing. Counting neighbouring
    seeds was blind, because seeds sit ALONG a contour at fall_spacing and
    neighbours on their own contour are always there -- 9 for a dense mass
    and the same 9 for a lone streak in empty space. Ink density failed
    differently: connectivity turned the decision into all-or-nothing per
    component, so mountains survived whole together with the stray strokes
    along their edge, while a gentle swell was removed entirely because its
    hachuring is legitimately sparser.

    What separates litter from honest hachuring is neither density nor blob
    shape but the NUMBER OF RELIEF STEPS described. A single stroke on a
    single contour depicts no form -- that is the definition of stray. A
    massif crosses many contours; so does the sparse but honest hachuring of
    a gentle swell.

    The measure is resolution invariant, which is the point: the plugin
    works with open DEMs at 30, 90, 450 and 1800 m per pixel. Bench spacing
    in pixels stays inside a narrow 3-10 px band there only because the
    contour interval grows together with the pixel, so any threshold stated
    in pixels or metres misses when the data source changes. A count of
    contour levels depends on neither.

    Search radius is 2.5 LOCAL bench spacings (bench_px is computed
    pointwise from the slope), so the window widens on gentle ground and
    tightens on steep.

    Coordinates are taken in the data grid, not screen space: bench spacing
    is defined there, and displacement by height would compress the window
    and the measure by different amounts.
    """
    n = len(levels)
    s = float(np.clip(strength, 0.0, 1.0))
    if s <= 0.0 or n < 5:
        return np.ones(max(n, 0), dtype=bool)
    min_lev = 2 + int(2.0 * s)          # 2 / 3 / 4 steps by strength
    from scipy.spatial import cKDTree
    pts = np.asarray(seeds, dtype="float64")
    lev = np.asarray(levels)
    rad = 2.5 * np.clip(np.asarray(bench_px, dtype="float64"), 2.0, 60.0)
    nb = cKDTree(pts).query_ball_point(pts, r=rad)
    keep = np.fromiter(
        (len(set(lev[np.asarray(ix, dtype=np.int64)])) >= min_lev
         if len(ix) else False for ix in nb), dtype=bool, count=n)
    if log:
        log("Stray-stroke thinning: need >=%d contour levels within "
            "2.5*bench (median window %.0f px), removed %d of %d (%.1f%%)"
            % (min_lev, float(np.median(rad)), int((~keep).sum()), n,
               100.0 * float((~keep).mean())))
    if not keep.any():
        return np.ones(n, dtype=bool)
    return keep


def cast_shadow(z, px, py, az_deg, alt_deg, softness_px=1.5, max_ratio=1.0):
    """Cast shadow: a 0..1 mask of where terrain blocks the sun.

    This is NOT the same as floating_horizon. That one runs strictly along
    the row axis, because after the scene is rotated the line of sight
    points along it. The sun stands at its own azimuth, so a separate pass
    is needed.

    The method is a march along the ray towards the sun: a point is in
    shadow if at some distance d the terrain rises above the line
    z + d*tan(alt).

    Diffuse illumination answers "how is this slope turned towards the sun";
    this mask answers "does light reach it at all". Two different
    quantities: a north-facing slope is always dark, while the shadow of a
    neighbouring ridge falls on south-facing ground as well.

    Near the point the step is strictly one pixel. That is not caution: with
    a purely geometric step the march skips whole pixels (1, 2, 3, 4, 5, 7,
    10, 13 ...), and an obstacle one pixel thick that lands in a gap casts
    no shadow at all -- against the analytic answer that gave 11 px instead
    of 34.6. Beyond the dense zone (64 px) the step grows geometrically:
    further out only large forms remain, and those do not fall through.
    """
    rows, cols = z.shape
    az = np.radians(float(az_deg))
    dj = np.sin(az)                 # columns: east
    di = -np.cos(az)                # rows: north means a falling index
    tan_alt = np.tan(np.radians(max(float(alt_deg), 1.0)))
    step_m = np.hypot(dj * float(px), di * float(py))
    zr = np.nanmax(z) - np.nanmin(z)
    if not np.isfinite(zr) or zr <= 0 or step_m <= 0:
        return np.zeros_like(z, dtype="float64")
    # beyond this distance no obstacle can occlude the point any more
    reach = min(zr / tan_alt / step_m, float(max(rows, cols)) * max_ratio)
    horizon = np.full_like(z, -np.inf, dtype="float64")
    k = 1.0
    while k <= reach:
        oi = int(round(di * k)); oj = int(round(dj * k))
        if abs(oi) >= rows or abs(oj) >= cols:
            break
        src = np.full_like(z, -np.inf, dtype="float64")
        si = slice(max(0, oi), rows + min(0, oi))
        di_ = slice(max(0, -oi), rows + min(0, -oi))
        sj = slice(max(0, oj), cols + min(0, oj))
        dj_ = slice(max(0, -oj), cols + min(0, -oj))
        src[di_, dj_] = z[si, sj]
        np.maximum(horizon, src - k * step_m * tan_alt, out=horizon)
        k = k + 1.0 if k < 64.0 else k * 1.35
    sh = (horizon > z).astype("float64")
    if softness_px and softness_px > 0:
        ndimage.gaussian_filter(sh, sigma=float(softness_px), output=sh)
    return np.clip(sh, 0.0, 1.0)


def scene_report(z, slope_deg, px, py, interval, min_slope_deg, log):
    """Scene diagnostics in the log: the numbers that show whether the
    settings match the scale of the data, plus hints.

    Added after a run of stroke-engine fixes in which the real quantities of
    the scene repeatedly turned out not to be the assumed ones: bench
    spacing came to 6 px instead of 34, the area below the slope threshold
    to 70% instead of a third. Cheaper to print them up front than to chase
    the consequences several releases later.
    """
    mpp = (float(px) + float(py)) / 2.0
    zz = z[np.isfinite(z)]
    ss = slope_deg[np.isfinite(slope_deg)]
    if zz.size == 0 or ss.size == 0:
        return
    z5, z95 = np.percentile(zz, [5, 95])
    s50, s90 = np.percentile(ss, [50, 90])
    bench = bench_spacing_px(s50, interval, mpp)
    flat = 100.0 * float((ss < min_slope_deg).mean())
    log("Scene: %d x %d px, %.0f m/pixel (%.0f x %.0f km); elevations "
        "%.0f..%.0f m (P5/P95 %.0f/%.0f)"
        % (z.shape[1], z.shape[0], mpp, z.shape[1] * mpp / 1000.0,
           z.shape[0] * mpp / 1000.0, np.nanmin(zz), np.nanmax(zz), z5, z95))
    log("Scene: slope median %.1f deg, P90 %.1f deg; %.0f%% of the area is "
        "below the stroke threshold; bench spacing at median slope %.1f px"
        % (s50, s90, flat, bench))
    hints = []
    if bench < 3.0:
        hints.append("bench spacing below 3 px -- contours will merge, "
                     "raise the contour interval")
    elif bench > 20.0:
        hints.append("bench spacing above 20 px -- strokes will be long and "
                     "sparse, lower the contour interval")
    if flat > 65.0:
        hints.append("the scene is mostly gentle -- switch on relative mode "
                     "or lower the slope threshold")
    if (np.nanmax(zz) - np.nanmin(zz)) < 150.0:
        hints.append("elevation range below 150 m -- raise the vertical "
                     "exaggeration")
    for h in hints:
        log("Scene, hint: " + h)

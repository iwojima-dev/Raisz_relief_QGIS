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


def estimate_memory_gb(grid, dpi, n_arrays=11):
    """Rough peak-memory estimate: working arrays + the mpl raster canvas."""
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

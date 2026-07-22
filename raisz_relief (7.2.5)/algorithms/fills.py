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
fills.py -- the unified fill pipeline: plan-view RGBA -> draped by disp.

Both hypsometric (palettes.build_elevation_rgba) and thematic
(polygons rasterized with layer-style colors) fills are reduced to one
form -- RGBA on the working grid -- and draped by the same displacement
field disp as the hachures, so they fit the relief exactly.

Dependencies: numpy, rasterio.features.
"""

import numpy as np

from .palettes import build_elevation_rgba, _hex2rgb  # noqa: F401


def build_thematic_rgba(polys, grid, alpha=0.85, affine=None, out_shape=None):
    """Rasterize thematic polygons (geojson rings, color) onto the working
    grid and assemble RGBA (ny x nx x 4). polys: list of (rings, '#rrggbb').
    affine/out_shape override the grid (needed with view rotation)."""
    from rasterio.features import rasterize

    ny, nx = out_shape if out_shape else (grid.ny, grid.nx)
    aff = affine if affine is not None else grid.affine
    rgba = np.zeros((ny, nx, 4), dtype="float64")
    if not polys:
        return rgba

    # unique colors -> codes (1..N), 0 = background/transparent
    colors = []
    color_id = {}
    shapes = []
    for rings, chex in polys:
        if chex not in color_id:
            colors.append(chex)
            color_id[chex] = len(colors)        # 1-based
        geom = {"type": "Polygon",
                "coordinates": [np.asarray(r).tolist() for r in rings]}
        shapes.append((geom, color_id[chex]))

    codes = rasterize(shapes, out_shape=(ny, nx), transform=aff,
                      fill=0, dtype="int32", all_touched=False)
    lut = np.zeros((len(colors) + 1, 3), dtype="float64")
    for chex, cid in color_id.items():
        lut[cid] = _hex2rgb(chex)
    rgba[..., :3] = lut[codes]
    rgba[..., 3] = np.where(codes > 0, alpha, 0.0)
    return rgba


def drape_image(rgba, disp):
    """Drape the fill by the disp field: screen row = row - disp.

    Hidden-surface removal goes in the SAME direction as the hachures
    (floating_horizon): the horizon builds from the observer at the bottom
    (minimum-accumulate over flipped rows). Otherwise peaks would take the
    color of a distant lower slope -- the fill would slide off the relief.
    Returns (img, extent) for imshow, Y axis down.
    """
    rows, cols = disp.shape
    rr = np.arange(rows)
    screen = rr[:, None] - disp
    # visibility: a row is visible if it rises above all closer rows
    flip = screen[::-1]                                # front edge first
    runmin = np.minimum.accumulate(flip, axis=0)
    prev = np.empty_like(runmin)
    prev[0] = np.inf
    prev[1:] = runmin[:-1]
    vis = (flip <= prev)[::-1]                         # back to row order

    t0 = int(np.floor(screen[vis].min())) - 1
    t1 = int(np.ceil(screen.max())) + 1
    H = t1 - t0
    tgt = np.arange(t0, t1)
    out = np.zeros((H, cols, 4), dtype=rgba.dtype)
    for c in range(cols):
        m = vis[:, c]
        sv = screen[m, c]                             # screen positions of visible rows
        rv = rr[m]                                     # their source rows
        o = np.argsort(sv)
        sr = np.interp(tgt, sv[o], rv[o], left=-1, right=-1)
        valid = sr >= 0
        si = np.clip(np.round(sr).astype(int), 0, rows - 1)
        out[valid, c, :] = rgba[si[valid], c, :]
    extent = (0, cols, t0 + H, t0)
    return out, extent


def _bulk_shade_mask(z, light_az_deg, win_px):
    """Shadow spot: the shaded-slope mask of LARGE landforms.
    Graphic (lithographic) manner: two hard tones -- half shadow (0.55)
    and shadow core (1.0), a crisp edge. The DEM is generalized by a
    Gaussian of ~win/3; steepness is cut by a hard threshold (plains stay
    clean); a light 1.5 px smoothing only removes raster jaggies, then an
    S-curve restores the crispness."""
    from scipy import ndimage
    zz = np.asarray(z, "float64")
    bad = ~np.isfinite(zz)
    if bad.any():
        zz = np.where(bad, float(np.nanmedian(zz)), zz)
    sigma = max(3.0, float(win_px) / 3.0)
    zs = ndimage.gaussian_filter(zz, sigma=sigma)
    gy, gx = np.gradient(zs)                  # d/drow, d/dcol
    az = np.radians(light_az_deg)
    lx, ly = np.sin(az), -np.cos(az)          # toward the light (screen: row down = south)
    gn = np.hypot(gx, gy)
    eps = 1e-12
    s = (gx * lx + gy * ly) / (gn + eps)      # slope shadedness (=-cos_i)
    pos = gn[gn > eps]
    g_ref = float(np.percentile(pos, 60)) if pos.size else eps
    steep = gn > 0.35 * g_ref                 # hard steepness threshold
    core = (s > 0.55) & steep                 # shadow core
    half = (s > 0.30) & steep                 # half shadow
    m = np.where(core, 1.0, np.where(half, 0.55, 0.0))
    m = ndimage.gaussian_filter(m, sigma=1.5)      # remove raster jaggies
    return np.clip((m - 0.15) / 0.70, 0.0, 1.0)    # restore crispness


def _shade_over(base, ink_hex, mask, density):
    """Composite the shadow layer (ink color, alpha = mask*density) over
    the base fill (alpha compositing). base=None -> shadow only (for the
    bare-paper mode)."""
    sa = np.clip(mask * density, 0.0, 1.0)
    ink = np.asarray(_hex2rgb(ink_hex), "float64")
    if base is None:
        out = np.zeros(mask.shape + (4,), "float64")
        out[..., :3] = ink
        out[..., 3] = sa
        return out
    ba = base[..., 3]
    oa = sa + ba * (1.0 - sa)
    safe = np.where(oa > 1e-12, oa, 1.0)
    out = np.empty_like(base)
    for c in range(3):
        out[..., c] = (ink[c] * sa + base[..., c] * ba * (1.0 - sa)) / safe
    out[..., 3] = oa
    return out


def build_base_fill(mode, z, disp, illum, grid, *, palette="patterson",
                    shade=0.35, override_min=None, override_max=None,
                    stretch=False, thematic_polys=None, alpha=0.85,
                    geff_rot=None, bulk_shade=0.0, bulk_win=120,
                    light_az=315.0, ink="#2a1d10", valid=None):
    """Assemble the base fill and return (img, extent) or (None, None).

    mode: 'none' | 'elevation' | 'thematic'. Thematic overrides elevation.
    geff_rot: rotated georeference (with view rotation) -- to rasterize
    thematics in the rotated z frame; None -> the original grid.
    valid: data mask; outside it the fill is fully transparent (nodata
    mode 'paper'), so the area without data stays clean paper.
    """
    if mode == "elevation":
        rgba = build_elevation_rgba(
            z, palette=palette, shade=shade, illum=illum,
            override_min=override_min, override_max=override_max,
            stretch=stretch)
    elif mode == "thematic":
        if geff_rot is not None:
            from affine import Affine
            aff = Affine.from_gdal(*geff_rot)
            rgba = build_thematic_rgba(thematic_polys or [], grid, alpha=alpha,
                                       affine=aff, out_shape=z.shape[:2])
        else:
            rgba = build_thematic_rgba(thematic_polys or [], grid, alpha=alpha)
    else:
        rgba = None
    if bulk_shade > 0.0:
        m = _bulk_shade_mask(z, light_az, bulk_win)
        if valid is not None:
            m = m * valid
        rgba = _shade_over(rgba, ink, m, bulk_shade)
    if rgba is None:
        return None, None
    if valid is not None:
        rgba = rgba.copy()
        rgba[..., 3] *= np.asarray(valid, "float64")
    return drape_image(rgba, disp)

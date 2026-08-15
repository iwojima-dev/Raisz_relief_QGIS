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
print_fx.py -- old-lithography print emulation:
  * draw_grain     -- paper grain (soft noise over the sheet, z=0.35);
  * draw_dotscreen -- halftone dot screen, a dot grid at 45 degrees
                     under the hachures (z=1.6, above the fill);
  * misregister    -- slight color misregistration: R/B channels of the
                     finished PNG shifted by 1-2 px (post-processing
                     after savefig; skipped for SVG/PDF).
All effects are raster by nature; in vector export grain/dotscreen are
embedded as raster underlays by matplotlib itself.
"""

from __future__ import annotations

import numpy as np

_SEED = 19141


def _rgb(color):
    from matplotlib.colors import to_rgb
    return to_rgb(color)


def draw_grain(ax, x0, x1, y_top, y_bot, ink, strength=0.055, z=0.35):
    """Paper grain over the whole sheet (margins included): irregular
    random noise, slightly smoothed with a box filter (no blocky
    structure, no repeating tiles). Deterministic (_SEED)."""
    rng = np.random.default_rng(_SEED)
    w = abs(x1 - x0)
    h = abs(y_bot - y_top)
    nx = 900
    ny = max(8, int(round(nx * h / max(w, 1e-9))))
    fine = rng.random((ny, nx))
    # soft 3x3 box smoothing -- texture without scipy and without tiling
    sm = fine.copy()
    sm[1:-1, 1:-1] = (
        fine[:-2, :-2] + fine[:-2, 1:-1] + fine[:-2, 2:]
        + fine[1:-1, :-2] + fine[1:-1, 1:-1] + fine[1:-1, 2:]
        + fine[2:, :-2] + fine[2:, 1:-1] + fine[2:, 2:]) / 9.0
    noise = 0.45 * fine + 0.55 * sm
    r, g, b = _rgb(ink)
    rgba = np.empty((ny, nx, 4), dtype=np.float32)
    rgba[..., 0] = r
    rgba[..., 1] = g
    rgba[..., 2] = b
    rgba[..., 3] = (noise ** 2) * strength
    ax.imshow(rgba, extent=(x0, x1, y_bot, y_top), origin="upper",
              interpolation="bilinear", zorder=z, aspect="auto")


def draw_dotscreen(ax, rows, cols, ink, spacing_px=6.0, alpha=0.10, z=1.6):
    """Halftone dot screen: a 45-degree dot grid over the raster area only,
    between the fill (~1) and the strokes (5). For very large rasters the
    array is built downsampled and the dots scale up proportionally."""
    side = max(rows, cols)
    ds = max(1, int(np.ceil(side / 2600.0)))
    spacing = max(spacing_px, 3.0 * ds)
    ny = max(2, int(rows // ds))
    nx = max(2, int(cols // ds))
    yy, xx = np.mgrid[0:ny, 0:nx]
    X = (xx + 0.5) * ds
    Y = (yy + 0.5) * ds
    s = spacing * np.sqrt(2.0)
    u = (X + Y) / s
    v = (X - Y) / s
    du = u - np.floor(u) - 0.5
    dv = v - np.floor(v) - 0.5
    mask = (du * du + dv * dv) < 0.30 ** 2
    r, g, b = _rgb(ink)
    rgba = np.zeros((ny, nx, 4), dtype=np.float32)
    rgba[..., 0] = r
    rgba[..., 1] = g
    rgba[..., 2] = b
    rgba[..., 3] = mask * alpha
    ax.imshow(rgba, extent=(0, cols, rows, 0), origin="upper",
              interpolation="nearest", zorder=z, aspect="auto")


def misregister(out_path, shift_px=1.0, log=None):
    """Old-lithography color misregistration: the red channel is shifted
    right and the blue channel left by shift_px. PNG only (file
    post-processing); skipped for vector formats with a log message."""
    if not str(out_path).lower().endswith(".png"):
        if log:
            log("Color misregistration: PNG only, skipped.")
        return
    s = int(round(shift_px))
    if s < 1:
        return
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt
    img = mpimg.imread(out_path)
    if img.ndim != 3 or img.shape[2] < 3:
        return
    img = np.array(img, dtype=np.float32, copy=True)
    img[..., 0] = np.roll(img[..., 0], s, axis=1)      # R to the right
    img[..., 2] = np.roll(img[..., 2], -s, axis=1)     # B to the left
    img[..., 2] = np.roll(img[..., 2], max(1, s // 2), axis=0)
    plt.imsave(out_path, np.clip(img, 0.0, 1.0))
    if log:
        log("Color misregistration applied: %d px." % s)

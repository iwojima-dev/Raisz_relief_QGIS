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
engrave.py -- anaglyptography (XIX-century medal engraving, the
banknote technique): a family of parallel horizontal lines bent by
the relief. The line of row r runs at screen height r - disp -- the
same oblique displacement as the whole map, so the engraving fits the
landforms exactly. Width is modulated by illumination: the line
thickens on shaded slopes and thins to nothing in the light. Hidden
surfaces are removed by the same floating horizon as the draping.
Pure vectorized array operations; true vectors in SVG/PDF.
"""

from __future__ import annotations

import numpy as np


def _visibility(disp):
    """Visibility mask and screen positions (floating horizon from the
    bottom, as in fills.drape_image)."""
    rows, _ = disp.shape
    rr = np.arange(rows)
    screen = rr[:, None] - disp
    flip = screen[::-1]
    runmin = np.minimum.accumulate(flip, axis=0)
    prev = np.empty_like(runmin)
    prev[0] = np.inf
    prev[1:] = runmin[:-1]
    return (flip <= prev)[::-1], screen


def draw_anaglypt(ax, disp, illum, ink, spacing=6, density=0.3,
                  z=1.8, scale=(1.0, 1.0), alpha=0.95):
    """Draw the engraved lines. spacing is the step in rows of the given
    grid; scale=(sx, sy) converts grid coordinates to sheet coordinates
    (for the downsampled grid of strip mode). Returns the segment count."""
    from matplotlib.collections import LineCollection
    vis, screen = _visibility(disp)
    rows, cols = disp.shape
    sx, sy = scale
    w_max = 0.5 + 2.0 * float(density)         # pt: density -> weight
    w_min = 0.07                               # thinner is not drawn (light)
    cc = np.arange(cols)
    seg_list = []
    w_list = []
    step = max(1, int(spacing))
    for r0 in range(step // 2, rows, step):
        y = screen[r0] * sy
        s = 1.0 - np.clip(illum[r0], 0.0, 1.0)  # shadedness 0..1
        w = w_max * np.clip((s - 0.22) / 0.78, 0.0, 1.0)
        ok = vis[r0] & (w > w_min)
        pair = ok[:-1] & ok[1:]
        idx = np.nonzero(pair)[0]
        if idx.size == 0:
            continue
        p0 = np.stack([cc[idx] * sx, y[idx]], axis=1)
        p1 = np.stack([cc[idx + 1] * sx, y[idx + 1]], axis=1)
        seg_list.append(np.stack([p0, p1], axis=1))
        w_list.append(0.5 * (w[idx] + w[idx + 1]))
    if not seg_list:
        return 0
    segs = np.concatenate(seg_list)
    ws = np.concatenate(w_list)
    ax.add_collection(LineCollection(
        segs, colors=[ink], linewidths=ws, alpha=alpha,
        capstyle="round", zorder=z))
    return int(len(segs))

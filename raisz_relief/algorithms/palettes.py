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
palettes.py -- hypsometric (elevation) palettes.

Each palette is a list of (elevation_m, '#rrggbb') at its native stops.
Default mapping is by ABSOLUTE elevation (m). The range can be
overridden manually (override_min/max -- the palette stretches linearly
to it) or stretched by data percentiles (draft mode).

No bathymetry: below the lowest stop the land color simply continues
downward (depressions get the lowest land tone). Water bodies are
drawn as separate sea polygons over the fill.
"""

import numpy as np

# (elevation_m, hex). Stop values approximate the spirit of each author.
PALETTES = {
    "patterson": [(0, "#acd0a5"), (150, "#c9e0a8"), (400, "#e3e0a0"),
                  (900, "#e0c78a"), (1600, "#c89b6b"), (2600, "#a8835a"),
                  (3500, "#b9a48f"), (4500, "#efe9e2")],
    "bartholomew": [(0, "#9bbf8a"), (150, "#bcd293"), (300, "#dbe09a"),
                    (600, "#ead98a"), (1200, "#d9b56b"), (1800, "#c2864b"),
                    (3000, "#9c5a32"), (4500, "#f2ead9")],
    "peucker": [(0, "#1a7a3a"), (200, "#5fa83f"), (500, "#b6c63f"),
                (1000, "#e6d43a"), (1700, "#e8a32a"), (2600, "#d6671f"),
                (3600, "#a83a2a"), (4800, "#f4ece6")],
    "imhof": [(0, "#9fb0a0"), (200, "#c2c6a6"), (500, "#d8d2b0"),
              (1100, "#d7c39a"), (1900, "#cdaf8c"), (2900, "#c6b3a0"),
              (3800, "#dcd2c8"), (4800, "#f3efe9")],
}
PALETTE_KEYS = ["patterson", "bartholomew", "peucker", "imhof"]
PALETTE_LABELS = ["Patterson", "Bartholomew", "Peucker", "Imhof"]
# Imhof relies on shading -> recommended hillshade blend
RECOMMENDED_SHADE = {"patterson": 0.35, "bartholomew": 0.25,
                     "peucker": 0.20, "imhof": 0.50}


def _hex2rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def _stops(key):
    pal = PALETTES.get(key, PALETTES["patterson"])
    elev = np.array([e for e, _ in pal], dtype="float64")
    rgb = np.array([_hex2rgb(c) for _, c in pal])
    return elev, rgb


def build_elevation_rgba(z, palette="patterson", shade=0.35, illum=None,
                         override_min=None, override_max=None, stretch=False):
    """Plan-view RGBA (rows x cols x 4) of the hypsometric fill.

    Domain modes:
      * absolute (default) -- color by elevation in meters via native stops;
      * override_min/max -- native stops stretched linearly to this range;
      * stretch=True -- stops ignored, stretched by 1-99 percentiles (draft).
    """
    elev, rgb = _stops(palette)
    e0, e1 = elev[0], elev[-1]

    if stretch:
        lo, hi = np.nanpercentile(z, 1), np.nanpercentile(z, 99)
        t = np.clip((z - lo) / max(hi - lo, 1e-6), 0, 1)
        pos = e0 + t * (e1 - e0)                 # into the native palette scale
    else:
        if override_min is not None and override_max is not None:
            # stretch native stops to the given range
            span = max(override_max - override_min, 1e-6)
            elev = override_min + (elev - e0) / (e1 - e0) * span
        pos = z

    out = np.empty(z.shape + (3,), dtype="float64")
    for k in range(3):
        out[..., k] = np.interp(pos, elev, rgb[:, k])
    rgba = np.concatenate([out, np.ones(z.shape + (1,))], axis=-1)

    if shade > 0 and illum is not None:
        sh = np.clip((illum + 1) / 2.0, 0, 1)[..., None]
        factor = (1.0 - shade) + shade * (0.55 + 0.9 * sh)
        rgba[..., :3] = np.clip(rgba[..., :3] * factor, 0, 1)
    return rgba

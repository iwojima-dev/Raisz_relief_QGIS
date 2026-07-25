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
theme.py -- symbology resolver for decoration layers per background.

resolve(background) -> a dict of styles per layer type. Principle: on
sepia, all hydrography and infrastructure are MONOCHROME in the stroke
color (they differ by pattern, not color -- the Raisz way); on colored
backgrounds water is blue, roads dark red, with halos over the fill.

Patterns (lake hatching, marsh tufts, coastal vignette) are a second
phase; here marshes/seas use solid/outline symbology.
"""

INK = "#2a1d10"          # stroke color (sepia ink)
PAPER = "#f4ecd6"        # default paper


def _hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _mix(a, b, t):
    """Mix two hex colors by fraction t toward b."""
    ar, ag, ab = _hexrgb(a)
    br, bg, bb = _hexrgb(b)
    m = (ar + (br - ar) * t, ag + (bg - ag) * t, ab + (bb - ab) * t)
    return "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in m)


def resolve(background, paper=PAPER, ink=INK):
    """background: 'sepia' | 'color'. Returns layer styles.
    Monochrome ('sepia') symbology derives from the (paper, ink) pair,
    so it works identically for every paper preset (sepia, blueprint,
    cyanotype, old map, white)."""
    if background == "sepia":
        return {
            "river":  dict(color=ink, lw=0.8, alpha=0.9),
            "lake":   dict(face=_mix(paper, ink, 0.14), edge=ink, lw=0.7, alpha=0.92),
            "sea":    dict(face=_mix(paper, ink, 0.18), edge=ink, lw=0.9, alpha=0.92),
            "marsh":  dict(face=_mix(paper, ink, 0.12), edge=ink, lw=0.4, alpha=0.9),
            "road":   dict(casing=paper, casing_lw=1.8, core=ink, core_lw=0.7),
            "settle": dict(color=ink, size=16, label=ink,
                           label_size=9, halo=paper),
            "baseline": dict(color=ink, lw=0.7, alpha=0.8),
            "landcover": {
                "forest": dict(color=ink, alpha=0.8, size=1.1),
                "grass":  dict(color=ink, lw=0.5, alpha=0.7),
                "rock":   dict(color=ink, lw=0.5, alpha=0.7),
                "ice":    dict(color=ink, lw=0.4, alpha=0.45),
                "sand":   dict(color=ink, lw=0.5, alpha=0.7),
                "salt":   dict(color=ink, lw=0.4, alpha=0.5),
                "scrub":  dict(color=ink, lw=0.5, alpha=0.7),
            },
        }
    # colored background (hypsometric or thematic fill)
    return {
        "river":  dict(color="#3f7ba6", lw=0.9, alpha=0.95),
        "lake":   dict(face="#a4cbe6", edge="#3f7ba6", lw=0.6, alpha=0.92),
        "sea":    dict(face="#a4cbe6", edge="#3f7ba6", lw=0.6, alpha=0.92),
        "marsh":  dict(face="#b6cebb", edge="#5f8f72", lw=0.5, alpha=0.9),
        "road":   dict(casing=paper, casing_lw=1.9, core="#95493a", core_lw=0.8),
        "settle": dict(color="#7a1f12", size=18, label="#3a2a1a",
                       label_size=9, halo=paper),
        "baseline": dict(color="#3a2a18", lw=0.7, alpha=0.75),
        "landcover": {
            "forest": dict(color="#3f6f3a", alpha=0.85, size=1.1),
            "grass":  dict(color="#7a8f3f", lw=0.5, alpha=0.8),
            "rock":   dict(color="#7a6f63", lw=0.5, alpha=0.8),
            "ice":    dict(color="#7fa8c8", lw=0.5, alpha=0.7),
            "sand":   dict(color="#c79a52", lw=0.5, alpha=0.85),
            "salt":   dict(color="#9a9488", lw=0.4, alpha=0.6),
            "scrub":  dict(color="#6b7a3a", lw=0.5, alpha=0.8),
        },
    }


def background_of(fill_mode):
    """Core fill_mode -> background category for the resolver."""
    return "sepia" if fill_mode == "none" else "color"

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
"""Relief presets of the plugin window.

A preset FILLS FIELDS once; it is not a mode. Nothing about it is stored
with the run, so the Processing algorithms, batch runs, models and
scripts are unaffected, and after applying a preset every field can be
edited as usual.

A preset touches only the CHARACTER of the relief rendering -- strokes,
stroke clean-up, local basis, slope thresholds, relative mode, vertical
exaggeration. The DEM, the output, the layers, the fill and the sheet
decoration are never changed, so choosing a preset does not undo a sheet
that is already set up.

Applying a preset sets every character field: the values the preset
names, and the algorithm's default for the rest. Applying "Mountains"
after "Gentle mountains" therefore really returns to the mountain
settings instead of keeping leftovers.

Values that depend on the DEM resolution are given in ground units and
converted with the pixel size of the chosen DEM:
  BASE_SCALE_M  local basis radius, metres -> BASE_SCALE in pixels;
  BENCH_PX      target contour spacing -> INTERVAL, through "Analyze DEM"
                (gui/analyze.py) at the median slope of the hachured
                ground.
Without a DEM these two are left as they are and the dialog says so.

User presets are the same dictionaries, saved in QgsSettings by name.
"""

import json
import math

from ..i18n import N_

# Every field a preset may set. A field the algorithm does not declare is
# skipped (the landform map has no LIGHT_SKIP, the classic one no
# MAX_WIDTH).
CHARACTER = [
    "VERT_EXAG", "BASE_SCALE", "INTERVAL",
    "FALL_SPACING", "SHADOW_DENSITY", "LIGHT_SKIP", "MIN_SLOPE",
    "SLOPE_ADAPT", "MAX_WIDTH", "MIN_DRAW_WIDTH", "SLOPE_WEIGHT",
    "VALLEY_BREAK", "FLAT_SHORT", "LONELY", "CAST_SHADOW",
    "REL_SCALE", "REL_TARGET", "REL_LEVELS",
]

CLEANUP_OFF = {"VALLEY_BREAK": 0.0, "FLAT_SHORT": 0.0, "LONELY": 0.0,
               "CAST_SHADOW": 0.0}

# id, title, description, values -- chosen on test renders (7.10.0):
#   Mountains      Himalaya near Pokhara, COP30 (27 m)
#   As in 7.3      Hawaii, Big Island (29 m) -- pixel-identical to 7.3.1
#   Rocky          Rio de Janeiro (30 m)
#   Low mountains  south coast of South Africa (85 m)
#   Gentle         Hawaii, Big Island (29 and 58 m)
# Every built-in sets the interval for about 5 px between contours on the
# hachured ground (gui/analyze.py), the basis radius where noted.
BUILTIN = [
    dict(id="mountains",
         title=N_("Mountains"),
         description=N_("High, steep relief. The plugin defaults: stroke "
                        "clean-up and cast shadow on, full stroke weight at "
                        "45 deg; dendritic dark lines along thalwegs are "
                        "suppressed."),
         values=dict(BENCH_PX=5.0)),
    dict(id="as_73",
         title=N_("As in 7.3 (no stroke clean-up)"),
         description=N_("The stroke settings of version 7.3: strokes run "
                        "their full length, dark accents in gullies and "
                        "thalwegs are kept, no cast shadow."),
         values=dict(CLEANUP_OFF, BENCH_PX=5.0)),
    dict(id="rocky",
         title=N_("Rocky, dissected"),
         description=N_("Domes, cliffs and gullies rising from lowland. "
                        "Long strokes without clean-up, denser in shade, "
                        "lit faces left blank."),
         values=dict(CLEANUP_OFF, LIGHT_SKIP=0.6, SHADOW_DENSITY=1.0,
                     BENCH_PX=5.0)),
    dict(id="low_mountains",
         title=N_("Low mountains"),
         description=N_("Ranges of a few hundred metres to 2 km over "
                        "rolling lowland. The defaults plus stroke weight "
                        "from the scene's slopes, so the lower ranges get "
                        "tone too."),
         values=dict(SLOPE_ADAPT=True, BENCH_PX=5.0)),
    dict(id="gentle",
         title=N_("Gentle mountains, shield volcanoes"),
         description=N_("Large forms at 3-10 deg: shield volcanoes, "
                        "plateaus, worn ranges. No clean-up, stroke weight "
                        "from the scene's slopes, a 2 deg stroke threshold "
                        "and a local basis on the scale of the forms "
                        "(17 km)."),
         values=dict(CLEANUP_OFF, SLOPE_ADAPT=True, MIN_SLOPE=2.0,
                     BASE_SCALE_M=17000.0, BENCH_PX=5.0)),
]

BASE_PX_RANGE = (15, 1500)


def builtin(preset_id):
    for p in BUILTIN:
        if p["id"] == preset_id:
            return p
    return None


def resolve(values, defaults, declared, mpp=None, interval_for=None):
    """Concrete field values for one preset.

    values      -- the preset's dictionary (may hold BASE_SCALE_M, BENCH_PX)
    defaults    -- {name: algorithm default}
    declared    -- names the algorithm declares
    mpp         -- metres per pixel of the drawing grid, or None
    interval_for(bench_px) -- callable returning a suggested interval, or
                    None when there is no DEM to analyse
    Returns (fields, notes): fields maps parameter name -> value; notes are
    the ground-unit values that could not be converted."""
    fields = {}
    for name in CHARACTER:
        if name not in declared or name in ("INTERVAL", "BASE_SCALE"):
            continue
        if name in values:
            fields[name] = values[name]
        elif name in defaults:
            fields[name] = defaults[name]
    notes = []
    if "BASE_SCALE" in declared:
        if "BASE_SCALE_M" in values:
            if mpp:
                px = int(round(float(values["BASE_SCALE_M"]) / float(mpp)))
                fields["BASE_SCALE"] = max(BASE_PX_RANGE[0],
                                           min(BASE_PX_RANGE[1], px))
            else:
                notes.append("BASE_SCALE")
        elif "BASE_SCALE" in values:
            fields["BASE_SCALE"] = values["BASE_SCALE"]
        elif "BASE_SCALE" in defaults:
            fields["BASE_SCALE"] = defaults["BASE_SCALE"]
    if "INTERVAL" in declared and "BENCH_PX" in values:
        iv = interval_for(float(values["BENCH_PX"])) if interval_for else None
        if iv:
            fields["INTERVAL"] = iv
        else:
            notes.append("INTERVAL")
    elif "INTERVAL" in declared and "INTERVAL" in values:
        fields["INTERVAL"] = values["INTERVAL"]
    return fields, notes


def suggest(stats):
    """Built-in preset that fits the scene statistics of gui/analyze.py,
    or None. A hint only -- it is printed, never applied."""
    s = stats.get("slope_med", 0.0)
    p90 = stats.get("slope_p90", 0.0)
    rng = stats.get("land_range", 0.0)
    if s <= 0.0:
        return None
    if s >= 20.0 and rng >= 1500.0:
        return "mountains"
    if p90 >= 18.0 and rng < 1500.0:
        return "rocky"
    if s < 9.0 and rng >= 1500.0:
        return "gentle"
    if rng < 2500.0:
        return "low_mountains"
    return "mountains"


# -- user presets -------------------------------------------------------

def to_json(values):
    return json.dumps(values, sort_keys=True)


def from_json(text):
    try:
        v = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(v, dict):
        return None
    clean = {}
    for k, x in v.items():
        if not isinstance(k, str):
            continue
        if isinstance(x, (bool, int, float)) and not (
                isinstance(x, float) and not math.isfinite(x)):
            clean[k] = x
    return clean


def capture(current, declared):
    """A user preset from the current field values: the character fields
    only, BASE_SCALE and INTERVAL kept in pixels and metres as they are --
    a user preset is a snapshot of one's own settings."""
    out = {}
    for name in CHARACTER:
        if name in declared and name in current:
            v = current[name]
            if isinstance(v, (bool, int, float)):
                out[name] = v
    return out

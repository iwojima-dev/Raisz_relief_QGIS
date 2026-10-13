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
"""Tab layout of the plugin dialog: which parameter goes where.

This file holds ONLY the placement. Labels, defaults, ranges, choice lists
and the widgets themselves come from the algorithm's own parameter
definitions at run time, so nothing here can drift from the algorithm.

Rules:
  * a name the current algorithm does not declare is skipped silently --
    the two algorithms share this layout but have different parameters;
  * a box left empty is not shown, nor is a tab left without boxes;
  * a parameter the algorithm declares but this layout does not mention
    lands in an extra "Other" tab, so a new parameter can never vanish
    from the dialog just because nobody added it here.
"""

from ..i18n import N_

TABS = [
    (N_("Main"), [
        (N_("Input and output"), [
            "DEM", "INTERVAL", "MAX_PX", "DPI", "OUTPUT",
        ]),
        (N_("Scene view"), [
            "VIEW_ANGLE", "VIEW_AZIMUTH", "VERT_EXAG", "BASE_SCALE",
            "SMOOTH",
        ]),
        (N_("Relative scene scale"), [
            "REL_SCALE", "REL_TARGET", "REL_LEVELS",
        ]),
        (N_("Large sheets"), [
            "STRIP_ROWS", "MEM_LIMIT",
        ]),
    ]),
    (N_("Strokes and light"), [
        (N_("Hachures"), [
            "DRAW_FALL", "DRAW_FRAMEWORK", "FALL_SPACING", "MAX_WIDTH",
            "MIN_DRAW_WIDTH", "SLOPE_WEIGHT", "MIN_SLOPE", "SLOPE_ADAPT",
            "SHADOW_DENSITY", "HAND_JITTER",
        ]),
        (N_("Light and shadow"), [
            "LIGHT_AZ", "LIGHT_ALT", "LIGHT_SKIP", "CAST_SHADOW",
        ]),
        (N_("Stroke clean-up"), [
            "VALLEY_BREAK", "FLAT_SHORT", "LONELY",
        ]),
    ]),
    (N_("Plains"), [
        (N_("Hammond classification"), [
            "HAMMOND_MODE", "HAMMOND_CLASS", "HAMMOND_WINDOW",
            "PLAIN_LO", "PLAIN_HI", "PLAIN_MID", "PLAIN_WIDTH",
            "HAMMOND_P_LO", "HAMMOND_P_HI",
        ]),
        (N_("Plains stipple"), [
            "DRAW_STIPPLE", "STIPPLE_R", "DOT_SIZE", "VALLEY_DENSIFY",
            "DENSIFY_SCALE",
        ]),
        (N_("Framework"), [
            "FRAMEWORK_ON_PLAINS", "DRAW_BASELINE",
        ]),
    ]),
    (N_("Fill and paper"), [
        (N_("Paper and fill"), [
            "PAPER_PRESET", "FILL_STYLE", "THEMATIC", "FILL_ALPHA",
            "HYPSO_SHADE", "STRETCH",
        ]),
        (N_("Manual elevation range"), [
            "OVR_ON", "OVR_MIN", "OVR_MAX",
        ]),
        (N_("Large-form shading"), [
            "SHADE_STYLE", "BULK_SHADE", "BULK_WIN", "ANAG_SPACING",
        ]),
        (N_("Watercolour"), [
            "WATERCOLOR",
        ]),
    ]),
    (N_("Layers"), [
        (N_("Waters"), [
            "RIVERS", "LAKES", "SEAS", "MARSHES", "AUTO_SEA", "SEA_LEVEL",
            "WATER_PATTERNS", "NODATA_MODE",
        ]),
        (N_("Land cover"), [
            "LC_FOREST", "LC_SAND", "LC_ICE", "LC_SCRUB", "LC_GRASS",
            "STYLE_FROM_LAYER",
        ]),
        (N_("Lines"), [
            "ROADS", "THEMATIC_LINE",
        ]),
        (N_("Settlements"), [
            "SETTLE_PT", "SETTLE_POLY", "SETTLE_LABEL", "SETTLE_FONT",
            "SETTLE_FONT_SCALE",
        ]),
    ]),
    (N_("Sheet and print"), [
        (N_("Sheet decoration"), [
            "SHEET_FRAME", "SHEET_TICKS", "SHEET_SCALEBAR", "SCALEBAR_BELOW",
            "SHEET_COMPASS", "SHEET_LEGEND",
        ]),
        (N_("Old-print emulation"), [
            "PRINT_DOT", "PRINT_GRAIN", "PRINT_MISREG",
        ]),
    ]),
]

OTHER_TAB = N_("Other")


def placed_names():
    """Every parameter name the layout mentions."""
    return {n for _tab, boxes in TABS for _box, names in boxes for n in names}


def plan_tabs(declared):
    """Resolve the layout for one algorithm.

    declared -- parameter names in declaration order (hidden ones already
    removed). Returns (plan, leftovers): plan is [(tab, [(box, [names])])]
    with empty boxes and tabs dropped; leftovers are the declared names the
    layout does not mention, already appended as an "Other" tab."""
    present = set(declared)
    plan = []
    for tab, boxes in TABS:
        kept = [(box, [n for n in names if n in present])
                for box, names in boxes]
        kept = [(box, names) for box, names in kept if names]
        if kept:
            plan.append((tab, kept))
    placed = placed_names()
    leftovers = [n for n in declared if n not in placed]
    if leftovers:
        plan.append((OTHER_TAB, [("Other parameters", leftovers)]))
    return plan, leftovers


# ------------------------------------------------------------ dependencies
#
# Fields that the algorithm does not read under the current settings are
# greyed out -- never hidden. A wrong rule therefore cannot make a field
# unreachable; at worst it shows grey while it still matters, and the value
# is passed to the algorithm either way.
#
# Each rule: (names it governs, test(v, nopt) -> True when ACTIVE, reason).
#   v(name)    -- current value of a parameter (None if absent)
#   nopt(name) -- number of options of an enum parameter
# Every rule below was checked against where the algorithm reads the value
# (processAlgorithm, _base.fill_kwargs, the render cores).

def _int(x, default=-1):
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def _set(x):
    """A layer / field value counts as set when it is neither None nor ''."""
    return x is not None and x != ""


def _fill(v, nopt):
    """0 = none, last = thematic, anything between = hypsometric."""
    i = _int(v("FILL_STYLE"), 0)
    if i == 0:
        return "none"
    return "thematic" if i == nopt("FILL_STYLE") - 1 else "elevation"


STROKE_PARAMS = ["FALL_SPACING", "MAX_WIDTH", "MIN_DRAW_WIDTH",
                 "SLOPE_WEIGHT", "MIN_SLOPE", "SHADOW_DENSITY", "LIGHT_SKIP",
                 "VALLEY_BREAK", "FLAT_SHORT", "LONELY", "HAND_JITTER",
                 "SLOPE_ADAPT"]

DEPENDENCIES = [
    # Hammond plains threshold modes: 0 two thresholds, 1 midpoint+width,
    # 2 Hammond classes, 3 auto percentiles
    (["PLAIN_LO", "PLAIN_HI"],
     lambda v, n: _int(v("HAMMOND_MODE")) == 0,
     N_("used only in the 'two thresholds' plains mode")),
    (["PLAIN_MID", "PLAIN_WIDTH"],
     lambda v, n: _int(v("HAMMOND_MODE")) == 1,
     N_("used only in the 'midpoint + width' plains mode")),
    (["HAMMOND_CLASS"],
     lambda v, n: _int(v("HAMMOND_MODE")) == 2,
     N_("used only in the 'Hammond classes' plains mode")),
    (["HAMMOND_P_LO", "HAMMOND_P_HI"],
     lambda v, n: _int(v("HAMMOND_MODE")) == 3,
     N_("used only in the 'auto from DEM' plains mode")),
    # relative scene scale replaces the contour interval by elevation belts
    (["INTERVAL"],
     lambda v, n: not v("REL_SCALE"),
     N_("relative scene scale derives the interval from the number of "
        "belts")),
    (["SLOPE_ADAPT"],
     lambda v, n: not v("REL_SCALE"),
     N_("relative scene scale normalizes slopes itself")),
    (["REL_TARGET", "REL_LEVELS"],
     lambda v, n: bool(v("REL_SCALE")),
     N_("used only with relative scene scale")),
    # fill
    (["FILL_ALPHA", "WATERCOLOR"],
     lambda v, n: _fill(v, n) != "none",
     N_("needs a relief fill")),
    (["HYPSO_SHADE", "STRETCH", "OVR_ON"],
     lambda v, n: _fill(v, n) == "elevation",
     N_("applies to the hypsometric fill only")),
    (["OVR_MIN", "OVR_MAX"],
     lambda v, n: _fill(v, n) == "elevation" and bool(v("OVR_ON")),
     N_("needs a hypsometric fill and the manual range switched on")),
    (["THEMATIC"],
     lambda v, n: _fill(v, n) == "thematic",
     N_("used only with the thematic fill")),
    # large-form shading: 0 none, 1 shadow spot, 2 anaglyptography
    (["BULK_SHADE"],
     lambda v, n: _int(v("SHADE_STYLE"), 0) in (1, 2),
     N_("needs a large-form shading style")),
    (["BULK_WIN"],
     lambda v, n: _int(v("SHADE_STYLE"), 0) == 1,
     N_("used only by the shadow spot")),
    (["ANAG_SPACING"],
     lambda v, n: _int(v("SHADE_STYLE"), 0) == 2,
     N_("used only by anaglyptography")),
    # sea level: auto-sea or nodata shown as sea (NODATA_KEYS index 1)
    (["SEA_LEVEL"],
     lambda v, n: bool(v("AUTO_SEA")) or _int(v("NODATA_MODE"), 0) == 1,
     N_("used by auto-sea and by nodata shown as sea")),
    # plains stipple
    (["STIPPLE_R", "DOT_SIZE", "VALLEY_DENSIFY"],
     lambda v, n: bool(v("DRAW_STIPPLE")),
     N_("needs plains stipple switched on")),
    (["DENSIFY_SCALE"],
     lambda v, n: bool(v("DRAW_STIPPLE")) and bool(v("VALLEY_DENSIFY")),
     N_("needs stipple and valley densifying switched on")),
    # settlements
    (["SETTLE_LABEL", "SETTLE_FONT", "SETTLE_FONT_SCALE"],
     lambda v, n: _set(v("SETTLE_PT")) or _set(v("SETTLE_POLY")),
     N_("needs a settlements layer")),
    # hachures
    (STROKE_PARAMS,
     lambda v, n: bool(v("DRAW_FALL")),
     N_("needs hachures switched on")),
]

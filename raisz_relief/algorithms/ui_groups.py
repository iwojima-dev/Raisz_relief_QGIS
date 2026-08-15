# -*- coding: utf-8 -*-
"""
ui_groups.py -- grouped parameter dialogs behind "Configure..." buttons.

The algorithm panel holds ~85 parameters. Most of them are chosen once and
never touched again, yet they all compete for attention with the handful
that are adjusted per DEM. This module moves five groups into dialogs of
their own, leaving a summary line and a button in the main panel:

    Fill: paper Sepia, watercolour 0.5          [Configure...]

Pure Qt: group descriptions, form building, summary text. It knows nothing
about Processing -- the wiring lives in ui_binding.py. The split is
deliberate: this half has no unknowns, the wiring half depends on QGIS
API details.

Qt5/Qt6: imports go through qgis.PyQt, which exists for exactly that
(metadata.txt: supportsQt6=True).

Values travel as {parameter_name: value} -- the same dictionary that
reaches processAlgorithm, so batch mode and the modeler still see ordinary
parameters.

Field lists, labels, defaults, ranges and choice lists below are COPIED
FROM THE CODE (_base.py, palettes.py). When parameters change there, these
descriptions must follow, or the dialog will show one thing while the
algorithm receives another. check_names() verifies the correspondence.
"""

from __future__ import annotations

from qgis.PyQt import QtCore, QtWidgets


# ------------------------------------------------------------ description

class Field:
    """One field of a group.

    kind: 'enum' | 'double' | 'int' | 'bool' | 'layer' | 'field'
    """

    def __init__(self, name, label, kind, default, options=None,
                 mn=None, mx=None, step=None, hint="", filt=None,
                 short=None):
        self.name = name
        self.label = label
        self.kind = kind
        self.default = default
        self.options = options or []
        self.mn = mn
        self.mx = mx
        self.step = step
        self.hint = hint
        self.filt = filt
        # short name for the summary line; None keeps it out of the summary
        self.short = short


class Group:
    """A set of fields opened by a single button."""

    def __init__(self, key, title, fields, note=""):
        self.key = key
        self.title = title
        self.fields = fields
        self.note = note


# ------------------------------------------------------------------- form

def _build_field(f, parent):
    """Widget for one field. Returns (widget, getter, setter)."""
    if f.kind == "enum":
        w = QtWidgets.QComboBox(parent)
        w.addItems([str(o) for o in f.options])
        return w, w.currentIndex, w.setCurrentIndex
    if f.kind == "bool":
        w = QtWidgets.QCheckBox(parent)
        return w, w.isChecked, w.setChecked
    if f.kind == "int":
        w = QtWidgets.QSpinBox(parent)
        w.setRange(int(f.mn if f.mn is not None else -10 ** 7),
                   int(f.mx if f.mx is not None else 10 ** 7))
        if f.step:
            w.setSingleStep(int(f.step))
        return w, w.value, lambda v: w.setValue(int(v))
    if f.kind == "double":
        w = QtWidgets.QDoubleSpinBox(parent)
        w.setDecimals(2)
        w.setRange(float(f.mn if f.mn is not None else -1e7),
                   float(f.mx if f.mx is not None else 1e7))
        w.setSingleStep(float(f.step or 0.1))
        return w, w.value, lambda v: w.setValue(float(v))
    if f.kind == "field":
        # attribute table field; a QgsFieldComboBox bound to the
        # settlements layer goes here when wired to Processing
        w = QtWidgets.QComboBox(parent)
        w.setEditable(True)
        w.addItem("")
        return w, w.currentText, lambda v: w.setEditText(str(v or ""))
    if f.kind == "layer":
        # placeholder for layer selection: a QgsMapLayerComboBox with the
        # right filter goes here when wired. A plain combo lets the form be
        # rendered and checked without QGIS.
        w = QtWidgets.QComboBox(parent)
        w.setEditable(True)
        w.addItem("")
        w.setToolTip(f.filt or "")
        return w, w.currentText, lambda v: w.setEditText(str(v or ""))
    raise ValueError("unknown field kind: %s" % f.kind)


class GroupDialog(QtWidgets.QDialog):
    """One group's window. Values are read and written as a dictionary."""

    def __init__(self, group, values=None, parent=None, available=None):
        """available -- names of parameters that EXIST in this algorithm.

        The groups are shared by both algorithms while their parameter
        sets differ: the classic one knows nothing of Hammond or plains
        stippling, the landform one nothing of strip tiling or the memory
        cap. Without the filter the dialog would offer fields with nowhere
        to write."""
        super().__init__(parent)
        if available is not None:
            group = Group(group.key, group.title,
                          [f for f in group.fields if f.name in available],
                          group.note)
        self.group = group
        self._io = {}                       # name -> (getter, setter)
        self.setWindowTitle(group.title)
        self.setMinimumWidth(560)

        lay = QtWidgets.QVBoxLayout(self)
        if group.note:
            note = QtWidgets.QLabel(group.note, self)
            note.setWordWrap(True)
            note.setStyleSheet("color: palette(mid);")
            lay.addWidget(note)

        # scrolling: 21 layer fields will not fit a small screen otherwise
        area = QtWidgets.QScrollArea(self)
        area.setWidgetResizable(True)
        area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame
                           if hasattr(QtWidgets.QFrame, "Shape")
                           else QtWidgets.QFrame.NoFrame)
        inner = QtWidgets.QWidget(area)
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            if hasattr(QtWidgets.QFormLayout, "FieldGrowthPolicy")
            else QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        for f in group.fields:
            w, get, setv = _build_field(f, inner)
            if f.hint:
                w.setToolTip(f.hint)
            lbl = QtWidgets.QLabel(f.label, inner)
            lbl.setWordWrap(True)
            if f.hint:
                lbl.setToolTip(f.hint)
            form.addRow(lbl, w)
            self._io[f.name] = (get, setv)

        area.setWidget(inner)
        lay.addWidget(area, 1)

        btns = QtWidgets.QDialogButtonBox(self)
        sb = QtWidgets.QDialogButtonBox.StandardButton
        btns.setStandardButtons(sb.Ok | sb.Cancel | sb.RestoreDefaults)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.button(sb.RestoreDefaults).clicked.connect(self.restore_defaults)
        lay.addWidget(btns)

        self.set_values(values or {})

    def set_values(self, values):
        for f in self.group.fields:
            v = values.get(f.name, f.default)
            try:
                self._io[f.name][1](v)
            except Exception:
                self._io[f.name][1](f.default)

    def values(self):
        return {n: io[0]() for n, io in self._io.items()}

    def restore_defaults(self):
        self.set_values({f.name: f.default for f in self.group.fields})


# ---------------------------------------------------------------- summary

def summarize(group, values, limit=3, available=None):
    """Line for the main panel: what is set, without opening the window.

    Only fields with a non-empty short name, and only those that DIFFER
    from the default -- otherwise the line fills with the obvious and stops
    being readable."""
    parts = []
    for f in group.fields:
        if not f.short:
            continue
        if available is not None and f.name not in available:
            continue
        v = values.get(f.name, f.default)
        if v == f.default:
            continue
        if f.kind == "enum":
            try:
                v = f.options[int(v)]
            except (IndexError, ValueError, TypeError):
                pass
        elif f.kind == "bool":
            if not v:
                continue
            parts.append(f.short)
            continue
        elif f.kind in ("layer", "field"):
            if not v:
                continue
            parts.append("%s: %s" % (f.short, v))
            continue
        parts.append("%s %s" % (f.short, v))
    if not parts:
        return "defaults"
    if len(parts) > limit:
        return ", ".join(parts[:limit]) + " and %d more" % (len(parts) - limit)
    return ", ".join(parts)


class GroupButton(QtWidgets.QWidget):
    """What the main panel shows: a summary line plus a button."""

    changed = QtCore.pyqtSignal()

    def __init__(self, group, values=None, parent=None):
        super().__init__(parent)
        self.group = group
        self._values = dict(values or
                            {f.name: f.default for f in group.fields})
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.lbl = QtWidgets.QLabel(self)
        self.lbl.setTextFormat(QtCore.Qt.TextFormat.PlainText
                               if hasattr(QtCore.Qt, "TextFormat")
                               else QtCore.Qt.PlainText)
        lay.addWidget(self.lbl, 1)
        self.btn = QtWidgets.QPushButton("Configure...", self)
        self.btn.clicked.connect(self.open_dialog)
        lay.addWidget(self.btn, 0)
        self._refresh()

    def _refresh(self):
        self.lbl.setText(summarize(self.group, self._values))
        self.lbl.setToolTip(self.group.note or self.group.title)

    def open_dialog(self):
        dlg = GroupDialog(self.group, self._values, self)
        acc = (QtWidgets.QDialog.DialogCode.Accepted
               if hasattr(QtWidgets.QDialog, "DialogCode")
               else QtWidgets.QDialog.Accepted)
        if dlg.exec() == acc:
            self._values = dlg.values()
            self._refresh()
            self.changed.emit()

    def values(self):
        return dict(self._values)

    def set_values(self, values):
        self._values.update(values or {})
        self._refresh()


# --------------------------------------------------------- plugin groups

E, D, I, B, L, F = "enum", "double", "int", "bool", "layer", "field"

PALETTE_LABELS = ["Patterson", "Bartholomew", "Peucker", "Imhof"]

FILL_STYLES = (["None - paper only"]
               + ["Hypsometric: " + s for s in PALETTE_LABELS]
               + ["Thematic (from layer style)"])

PAPER_PRESETS = ["Sepia", "Blueprint (white on blue)", "Cyanotype",
                 "Old map", "Plain white", "Diazotype (whiteprint)"]

NODATA_MODES = ["Plain (fill with nearest elevations)",
                "Sea (flood at sea level)",
                "Paper (do not draw -- clean sheet)"]

SHADE_STYLES = ["None", "Shadow spot (flat fill of shaded slopes)",
                "Anaglyptography (engraved line work)"]

FRAME_OPTS = ["None", "Single", "Double thin", "Thick-thin (classic)",
              "Map border (checkered degree fractions)"]

COMPASS_OPTS = ["None", "North arrow", "Compass rose (8 points)"]

SETTLE_FONTS = ["Default", "Serif", "Sans-serif", "Monospace",
                "Cursive", "Fantasy"]

HAMMOND_MODES = ["Manual: two thresholds (m)",
                 "Manual: midpoint + width (m)",
                 "Hammond classes", "Auto from DEM (draft)"]

HAMMOND_CLASSES = ["<=30 m -- plains", "<=90 m -- hills/low mountains",
                   "<=150 m -- mountains", "<=300 m -- high mountains"]


STROKE_GROUP = Group(
    "stroke", "Strokes and light",
    note=("The drawing itself: spacing, width, length and lighting. "
          "The 0-1 strengths at the bottom are the 7.4.0 stroke engine."),
    fields=[
        Field("DRAW_FALL", "Draw hachures (fall lines)", B, True),
        Field("DRAW_FRAMEWORK", "Draw the contour framework", B, True),
        Field("FALL_SPACING", "Base fall-line spacing, px", D, 4.0,
              mn=1.0, mx=40.0, step=0.5, short="spacing"),
        Field("MAX_WIDTH", "Max stroke width, pt", D, 1.9,
              mn=0.1, mx=10.0, step=0.1),
        Field("MIN_DRAW_WIDTH", "Cutoff: thinner is not drawn, pt", D, 0.35,
              mn=0.0, mx=5.0, step=0.05),
        Field("SLOPE_WEIGHT", "Slope vs light weight (0-1)", D, 0.45,
              mn=0.0, mx=1.0, step=0.05),
        Field("MIN_SLOPE", "Min slope for a stroke, deg", D, 4.0,
              mn=0.0, mx=90.0, step=0.5),
        Field("SHADOW_DENSITY", "Stroke crowding in shade (0-1)", D, 0.8,
              mn=0.0, mx=1.0, step=0.05),
        Field("LIGHT_SKIP", "Light threshold: brighter is skipped (0-1)", D,
              0.75, mn=0.0, mx=1.0, step=0.05),
        Field("LIGHT_AZ", "Light azimuth, deg", D, 315.0,
              mn=0.0, mx=360.0, step=5.0, short="light"),
        Field("LIGHT_ALT", "Light altitude, deg", D, 45.0,
              mn=0.0, mx=90.0, step=5.0),
        Field("VALLEY_BREAK", "Break strokes in thalwegs: strength 0-1", D,
              0.7, mn=0.0, mx=1.0, step=0.1, short="thalwegs"),
        Field("FLAT_SHORT", "Shorten strokes on gentle ground: 0-1", D, 0.6,
              mn=0.0, mx=1.0, step=0.1, short="shortening"),
        Field("LONELY", "Thin out stray strokes: strength 0-1", D, 0.4,
              mn=0.0, mx=1.0, step=0.1, short="stray"),
        Field("CAST_SHADOW", "Cast shadow from the terrain: 0-1", D, 0.5,
              mn=0.0, mx=1.0, step=0.1, short="shadow"),
    ])

PLAIN_GROUP = Group(
    "plain", "Plains and Hammond classification",
    note=("Where relief ends and plains begin, and how plains are drawn. "
          "Landform algorithm only."),
    fields=[
        Field("HAMMOND_MODE", "Classification: plain threshold mode", E, 1,
              options=HAMMOND_MODES, short="mode"),
        Field("HAMMOND_CLASS", "Hammond class (for 'classes' mode)", E, 1,
              options=HAMMOND_CLASSES),
        Field("HAMMOND_WINDOW", "Hammond classification window, m", D, 3000.0,
              mn=200.0, mx=100000.0, step=100.0, short="window"),
        Field("PLAIN_LO", "Two thresholds: below = plain, m (mode A)", D,
              30.0, mn=0.0, mx=10000.0, step=5.0),
        Field("PLAIN_HI", "Two thresholds: above = relief, m (mode A)", D,
              90.0, mn=0.0, mx=10000.0, step=5.0),
        Field("PLAIN_MID", "Midpoint: local relief at the boundary, m", D,
              90.0, mn=5.0, mx=10000.0, step=5.0),
        Field("PLAIN_WIDTH", "Transition width, +/- % of midpoint", D, 50.0,
              mn=5.0, mx=95.0, step=5.0),
        Field("HAMMOND_P_LO", "Auto: lower percentile, %", D, 40.0,
              mn=0.0, mx=100.0, step=1.0),
        Field("HAMMOND_P_HI", "Auto: upper percentile, %", D, 85.0,
              mn=0.0, mx=100.0, step=1.0),
        Field("DRAW_STIPPLE", "Draw plains (stipple)", B, True),
        Field("STIPPLE_R", "Plains stipple spacing, px (less = denser)", D,
              4.0, mn=1.5, mx=30.0, step=0.5, short="stipple"),
        Field("DOT_SIZE", "Dot size", D, 0.8, mn=0.1, mx=10.0, step=0.1),
        Field("VALLEY_DENSIFY", "Densify valley dots towards mountains", B,
              True),
        Field("DENSIFY_SCALE", "Densifying distance near mountains, m", D,
              2500.0, mn=0.0, mx=200000.0, step=100.0),
        Field("FRAMEWORK_ON_PLAINS", "Framework on plains too", B, False),
        Field("DRAW_BASELINE", "Outline mountain feet (dashed)", B, True),
    ])

FILL_GROUP = Group(
    "fill", "Fill, paper and shading",
    note="The wash under the strokes, and the paper it sits on.",
    fields=[
        Field("FILL_STYLE", "Relief fill", E, 0, options=FILL_STYLES,
              short="fill"),
        Field("PAPER_PRESET", "Paper type (paper/ink preset)", E, 0,
              options=PAPER_PRESETS, short="paper"),
        Field("FILL_ALPHA", "Fill opacity (0-1)", D, 0.85,
              mn=0.1, mx=1.0, step=0.05, short="alpha"),
        Field("HYPSO_SHADE", "Blend hillshade into hypsometry (0-1)", D,
              0.35, mn=0.0, mx=1.0, step=0.05, short="hillshade"),
        Field("STRETCH", "Stretch the palette to the data (draft)", B, False,
              short="stretched"),
        Field("OVR_ON", "Set the elevation range manually", B, False,
              short="manual range"),
        Field("OVR_MIN", "Elevation: min, m (manual range)", D, 0.0,
              mn=-12000, mx=9000, step=50),
        Field("OVR_MAX", "Elevation: max, m (manual range)", D, 4000.0,
              mn=-12000, mx=9000, step=50),
        Field("SHADE_STYLE", "Large-form shading", E, 0,
              options=SHADE_STYLES, short="shading"),
        Field("BULK_SHADE", "Shading intensity (0-1)", D, 0.3,
              mn=0.0, mx=1.0, step=0.05),
        Field("BULK_WIN", "Shadow spot: generalization window, px", I, 120,
              mn=20, mx=2000, step=10),
        Field("ANAG_SPACING", "Anaglyptography: line spacing, px", I, 6,
              mn=2, mx=40),
        Field("THEMATIC", "Thematic layer (polygons; colour from style)", L,
              "", filt="polygons", short="thematic"),
        Field("WATERCOLOR", "Watercolour the fill: strength 0-1", D, 0.0,
              mn=0.0, mx=1.0, step=0.1, short="watercolour"),
    ])

LAYERS_GROUP = Group(
    "layers", "Decoration layers, waters and labels",
    note="Every vector input and the settings tied to it, in one window.",
    fields=[
        Field("RIVERS", "Rivers (lines)", L, "", filt="lines",
              short="rivers"),
        Field("ROADS", "Roads (lines)", L, "", filt="lines", short="roads"),
        Field("THEMATIC_LINE", "Thematic line layer (colour from style)", L,
              "", filt="lines", short="thematic lines"),
        Field("LAKES", "Lakes (polygons)", L, "", filt="polygons",
              short="lakes"),
        Field("SEAS", "Seas (polygons)", L, "", filt="polygons",
              short="seas"),
        Field("MARSHES", "Marshes (polygons)", L, "", filt="polygons",
              short="marshes"),
        Field("LC_FOREST", "Land cover: forest", L, "", filt="polygons",
              short="forest"),
        Field("LC_SAND", "Land cover: sand/dunes", L, "", filt="polygons"),
        Field("LC_ICE", "Land cover: ice/glaciers", L, "", filt="polygons"),
        Field("LC_SCRUB", "Land cover: scrub", L, "", filt="polygons"),
        Field("LC_GRASS", "Land cover: grassland/steppe", L, "",
              filt="polygons"),
        Field("SETTLE_PT", "Settlements (points)", L, "", filt="points",
              short="settlements"),
        Field("SETTLE_POLY", "Settlements (polygons)", L, "",
              filt="polygons"),
        Field("SETTLE_LABEL", "Settlement label field", F, "",
              short="labels"),
        Field("SETTLE_FONT", "Settlement label font", E, 0,
              options=SETTLE_FONTS),
        Field("SETTLE_FONT_SCALE", "Label and symbol size (1.0 = auto)", D,
              1.0, mn=0.2, mx=5.0, step=0.1),
        Field("AUTO_SEA", "Auto sea from the DEM", B, False,
              short="auto sea"),
        Field("SEA_LEVEL", "Sea level, m (for auto sea)", D, 0.0,
              mn=-12000, mx=9000, step=10),
        Field("WATER_PATTERNS", "Hydrography patterns", B, False,
              short="water patterns"),
        Field("STYLE_FROM_LAYER", "Styling from layer styles", B, False,
              short="layer styling"),
        Field("NODATA_MODE", "Show nodata areas as", E, 0,
              options=NODATA_MODES, short="nodata"),
    ])

SHEET_GROUP = Group(
    "sheet", "Sheet decoration and print",
    note="All off by default.",
    fields=[
        Field("SHEET_FRAME", "Sheet decoration: frame", E, 0,
              options=FRAME_OPTS, short="frame"),
        Field("SHEET_TICKS", "Sheet decoration: graticule ticks", B, False,
              short="ticks"),
        Field("SHEET_SCALEBAR", "Sheet decoration: scale bar", B, False,
              short="scale bar"),
        Field("SCALEBAR_BELOW", "Sheet decoration: scale bar below the map",
              B, False),
        Field("SHEET_COMPASS", "Sheet decoration: compass rose", E, 0,
              options=COMPASS_OPTS, short="compass"),
        Field("HAND_JITTER", "Hand tremor in strokes (0-1, 0 = clean)", D,
              0.0, mn=0.0, mx=1.0, step=0.05, short="tremor"),
        Field("PRINT_DOT", "Print: halftone screen under the hachures", B,
              False, short="halftone"),
        Field("PRINT_GRAIN", "Print: paper grain", B, False, short="grain"),
        Field("PRINT_MISREG", "Print: colour misregistration, px", D, 0.0,
              mn=0.0, mx=4.0, step=0.1, short="misregistration"),
    ])


# Five groups go behind buttons. View, scene geometry, strip tiling and the
# memory cap stay as ordinary fields in the main panel: those are tuned per
# DEM rather than chosen once and forgotten.
GROUPS = [STROKE_GROUP, PLAIN_GROUP, FILL_GROUP, LAYERS_GROUP, SHEET_GROUP]


def group_by_key(key):
    for g in GROUPS:
        if g.key == key:
            return g
    return None


def all_field_names(group):
    """Parameter names of a group -- the wiring writes values back under
    these keys."""
    return [f.name for f in group.fields]


def check_names(alg):
    """Verify the descriptions against a real algorithm: which described
    fields it lacks, and which of its parameters ended up in no group.

    Needed because the lists above are a copy of the declarations in
    _base.py, and a copy drifts from its original sooner or later.

        from raisz_relief.algorithms import ui_groups, physiographic_algorithm
        ui_groups.check_names(physiographic_algorithm.PhysiographicAlgorithm())
    """
    try:
        alg.initAlgorithm({})
    except Exception as e:
        print("check_names: initAlgorithm failed: %s" % e)
    real = {p.name() for p in alg.parameterDefinitions()}
    described = set()
    print("=" * 60)
    for g in GROUPS:
        miss = [f.name for f in g.fields if f.name not in real]
        described |= {f.name for f in g.fields}
        print("%-8s %2d fields, absent from the algorithm: %s"
              % (g.key, len(g.fields), ", ".join(miss) if miss else "-"))
    rest = sorted(n for n in real
                  if n not in described and not n.startswith("RZGRP_"))
    print("-" * 60)
    print("In no group (%d):" % len(rest))
    for n in rest:
        print("   ", n)
    return rest

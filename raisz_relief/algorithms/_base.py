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
_base.py -- shared base class of both Processing algorithms: decoration
parameters (fill, separate water/road/settlement layers, thematic layer,
sheet decoration, print emulation) and their extraction into overlays
clipped to the DEM extent. Both the landform and the classic algorithm
inherit from this class.
"""

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing, QgsProcessingAlgorithm,
    QgsProcessingParameterNumber, QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum, QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField, QgsProcessingParameterDefinition,
)

from .palettes import PALETTE_KEYS, PALETTE_LABELS


class ReliefAlgorithmBase(QgsProcessingAlgorithm):
    # decoration parameter names
    FILL_STYLE = "FILL_STYLE"
    FILL_ALPHA = "FILL_ALPHA"
    SHADE_STYLE = "SHADE_STYLE"
    BULK_SHADE = "BULK_SHADE"
    BULK_WIN = "BULK_WIN"
    ANAG_SPACING = "ANAG_SPACING"
    HYPSO_SHADE = "HYPSO_SHADE"
    OVR_ON = "OVR_ON"
    OVR_MIN = "OVR_MIN"
    OVR_MAX = "OVR_MAX"
    STRETCH = "STRETCH"
    THEMATIC = "THEMATIC"
    RIVERS = "RIVERS"
    LAKES = "LAKES"
    SEAS = "SEAS"
    MARSHES = "MARSHES"
    ROADS = "ROADS"
    SETTLE_PT = "SETTLE_PT"
    SETTLE_POLY = "SETTLE_POLY"
    SETTLE_LABEL = "SETTLE_LABEL"
    WATER_PATTERNS = "WATER_PATTERNS"
    LC_FOREST = "LC_FOREST"; LC_SAND = "LC_SAND"; LC_ICE = "LC_ICE"
    LC_SCRUB = "LC_SCRUB"; LC_GRASS = "LC_GRASS"
    PAPER_PRESET = "PAPER_PRESET"
    AUTO_SEA = "AUTO_SEA"; SEA_LEVEL = "SEA_LEVEL"
    NODATA_MODE = "NODATA_MODE"
    NODATA_MODES = ["Plain (fill with nearest elevations)",
                    "Sea (flood at sea level)",
                    "Paper (do not draw -- clean sheet)"]
    NODATA_KEYS = ["plain", "sea", "paper"]
    HAND_JITTER = "HAND_JITTER"
    SHEET_FRAME = "SHEET_FRAME"
    SHEET_TICKS = "SHEET_TICKS"
    SHEET_SCALEBAR = "SHEET_SCALEBAR"
    SHEET_LEGEND = "SHEET_LEGEND"
    SHEET_COMPASS = "SHEET_COMPASS"
    PRINT_DOT = "PRINT_DOT"
    PRINT_GRAIN = "PRINT_GRAIN"
    PRINT_MISREG = "PRINT_MISREG"

    # combined fill style: none / hypsometric palettes / thematic
    FILL_STYLES = (["None - paper only"]
                   + ["Hypsometric: " + s for s in PALETTE_LABELS]
                   + ["Thematic (from layer style)"])
    FRAME_OPTS = ["None", "Single", "Double thin",
                  "Thick-thin (classic)",
                  "Map border (checkered degree fractions)"]
    COMPASS_OPTS = ["None", "North arrow", "Compass rose (8 points)"]
    SHADE_STYLES = ["None", "Shadow spot (flat fill of shaded slopes)",
                    "Anaglyptography (engraved line work)"]
    PAPER_PRESETS = ["Sepia", "Blueprint (white on blue)", "Cyanotype",
                     "Old map", "Plain white", "Diazotype (whiteprint)"]
    # (paper, ink) colors for each preset
    PAPER_INK = [
        ("#f4ecd6", "#2a1d10"),   # sepia
        ("#15467e", "#f4f8ff"),   # blueprint: blue paper, white strokes
        ("#2f6b78", "#dfeee8"),   # cyanotype: muted cyan
        ("#e7dabc", "#5a3820"),   # old map: yellower paper, brown ink
        ("#ffffff", "#1a1a1a"),   # plain white
        ("#f3e7e7", "#63426a"),   # diazotype: pale pink + purple ink
    ]

    def tr(self, s):
        return QCoreApplication.translate("Relief", s)

    def group(self):
        return self.tr("Raisz-style relief")

    def groupId(self):
        return "raisz_relief"

    def _adv(self, p):
        p.setFlags(p.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        return p

    def _h(self, p, text):
        """Attach a tooltip / help string to the parameter."""
        p.setHelp(self.tr(text))
        return p

    def _vec(self, name, label, types, help_text=None):
        p = QgsProcessingParameterVectorLayer(
            name, self.tr(label), types=types, optional=True)
        if help_text:
            p.setHelp(self.tr(help_text))
        return p

    def add_fill_params(self):
        """Primary fill -- three fields: paper, fill style, thematic layer.
        Fine-tuning goes to the advanced section."""
        D = QgsProcessingParameterNumber.Double
        self.addParameter(self._h(QgsProcessingParameterEnum(
            self.PAPER_PRESET, self.tr("Paper type (paper/ink preset)"),
            options=self.PAPER_PRESETS, defaultValue=0),
            "Background paper and ink color pair. All line work, water and "
            "sheet decoration take their colors from this preset, so every "
            "preset stays stylistically consistent."))
        self.addParameter(self._h(QgsProcessingParameterEnum(
            self.FILL_STYLE, self.tr("Relief fill"),
            options=self.FILL_STYLES, defaultValue=0),
            "None: bare paper (classic monochrome sheet). Hypsometric: "
            "elevation tints draped over the displaced relief (choose a "
            "palette). Thematic: polygons of the thematic layer rasterized "
            "with colors taken from their QGIS layer style."))
        self.addParameter(self._vec(
            self.THEMATIC, "Thematic layer (polygons; colors from layer style)",
            [QgsProcessing.TypeVectorPolygon],
            "Used only when Relief fill = Thematic. Fill colors are read "
            "from the layer's own QGIS symbology (categorized or single "
            "symbol)."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterNumber(
            self.FILL_ALPHA, self.tr("Fill opacity (0-1)"),
            D, 0.85, minValue=0.1, maxValue=1.0)),
            "Opacity of the hypsometric or thematic fill over the paper."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterEnum(
            self.SHADE_STYLE,
            self.tr("Large-form shading"),
            options=self.SHADE_STYLES, defaultValue=0)),
            "Optional tonal treatment of shaded slopes of LARGE landforms "
            "(the DEM is generalized first). Shadow spot: a two-tone flat "
            "lithographic shadow. Anaglyptography: XIX-century medal-"
            "engraving line work -- parallel lines bent by the relief, "
            "thicker in shade, vanishing in light. The two are mutually "
            "exclusive."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterNumber(
            self.BULK_SHADE,
            self.tr("Shading intensity (0-1)"),
            D, 0.3, minValue=0.0, maxValue=1.0)),
            "Strength of the selected large-form shading: shadow tone "
            "opacity for the spot, maximum line weight for the engraving. "
            "Try 0.4-0.5 for the spot, 0.25-0.35 for the engraving."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterNumber(
            self.BULK_WIN,
            self.tr("Shadow spot: generalization window, px"),
            QgsProcessingParameterNumber.Integer, 120,
            minValue=20, maxValue=2000)),
            "Gaussian generalization of the DEM before the shadow is cast "
            "(shadow spot only). Larger window -> only the biggest ridges "
            "cast a shadow."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterNumber(
            self.ANAG_SPACING,
            self.tr("Anaglyptography: line spacing, px"),
            QgsProcessingParameterNumber.Integer, 6,
            minValue=2, maxValue=40)),
            "Spacing of the engraved parallel lines in pixels of the "
            "output sheet (anaglyptography only)."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterNumber(
            self.HYPSO_SHADE, self.tr("Blend hillshade into hypsometry (0-1)"),
            D, 0.35, minValue=0.0, maxValue=1.0)),
            "Mixes analytic hillshading into the hypsometric tints "
            "(hypsometric fill only)."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterBoolean(
            self.OVR_ON, self.tr("Set elevation range manually"), False)),
            "Override the automatic elevation range of the hypsometric "
            "palette with the min/max values below. Useful for keeping "
            "colors comparable across adjacent sheets."))
        self.addParameter(self._adv(QgsProcessingParameterNumber(
            self.OVR_MIN, self.tr("Elevation: min, m (manual range)"),
            D, 0.0)))
        self.addParameter(self._adv(QgsProcessingParameterNumber(
            self.OVR_MAX, self.tr("Elevation: max, m (manual range)"),
            D, 4000.0)))
        self.addParameter(self._h(self._adv(QgsProcessingParameterBoolean(
            self.STRETCH, self.tr("Stretch palette to data (draft)"),
            False)),
            "Percentile stretch of the palette over the actual data range. "
            "Draft mode -- colors lose their absolute elevation meaning."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterNumber(
            self.HAND_JITTER,
            self.tr("Hand jitter of stroke width (0-1, 0 = even)"),
            D, 0.0, minValue=0.0, maxValue=1.0)),
            "Random variation of stroke WIDTH along fall lines, imitating "
            "a hand-held pen. This is width modulation, not positional "
            "wobble."))

    def add_overlay_params(self):
        """Decoration layers: all vector layers first as one block
        (waters, land cover, infrastructure), then flags and settings."""
        self.addParameter(self._vec(self.RIVERS, "Rivers (lines)",
                                    [QgsProcessing.TypeVectorLine],
                                    "Drawn in ink on paper presets, in blue "
                                    "over colored fills; pass under area "
                                    "waters."))
        self.addParameter(self._vec(self.LAKES, "Lakes (polygons)",
                                    [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(self._vec(self.SEAS, "Seas (polygons)",
                                    [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(self._vec(self.MARSHES, "Marshes (polygons)",
                                    [QgsProcessing.TypeVectorPolygon],
                                    "Rendered with tuft symbols when "
                                    "hydrography patterns are enabled."))
        self.addParameter(self._vec(self.LC_FOREST, "Land cover: forest (polygons)",
                                    [QgsProcessing.TypeVectorPolygon],
                                    "Stippled forest texture drawn above "
                                    "the hachures."))
        self.addParameter(self._vec(self.LC_SAND, "Land cover: sand/dunes (polygons)",
                                    [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(self._vec(self.LC_ICE, "Land cover: ice/glaciers (polygons)",
                                    [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(self._vec(self.LC_SCRUB, "Land cover: scrub (polygons)",
                                    [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(self._vec(self.LC_GRASS, "Land cover: grassland/steppe (polygons)",
                                    [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(self._vec(self.ROADS, "Roads (lines)",
                                    [QgsProcessing.TypeVectorLine],
                                    "Cased road symbol drawn above waters."))
        self.addParameter(self._vec(self.SETTLE_PT, "Settlements (points)",
                                    [QgsProcessing.TypeVectorPoint],
                                    "Point symbols with optional labels "
                                    "haloed in the paper color."))
        self.addParameter(self._vec(self.SETTLE_POLY, "Settlements (polygons)",
                                    [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(self._h(QgsProcessingParameterField(
            self.SETTLE_LABEL, self.tr("Settlement label field"),
            parentLayerParameterName=self.SETTLE_PT, optional=True),
            "Attribute of the settlement point layer used for labels. "
            "Labels are set a couple of points larger than symbols and "
            "haloed with the paper color."))
        self.addParameter(self._h(QgsProcessingParameterBoolean(
            self.AUTO_SEA,
            self.tr("Auto-sea from DEM (water polygon at level)"), False),
            "Builds a sea polygon from the DEM at the given level; island "
            "holes are preserved. Covers hachures and stipple like any "
            "area water."))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.SEA_LEVEL, self.tr("Sea level, m (for auto-sea)"),
            QgsProcessingParameterNumber.Double, 0.0),
            "Elevation threshold of the auto-sea."))
        self.addParameter(self._h(QgsProcessingParameterEnum(
            self.NODATA_MODE,
            self.tr("Areas without data (nodata) shown as"),
            options=self.NODATA_MODES, defaultValue=0),
            "What to do where the DEM has no data. 'Plain' fills with the "
            "nearest elevations (the default and the old behaviour), which "
            "reads as a flat plain. 'Sea' floods the gap at sea level and "
            "adds it to the sea polygons. 'Paper' leaves it undrawn: no "
            "fill, no strokes, no framework -- a clean sheet, as on maps "
            "where the survey did not cover a corner. In every mode the "
            "nodata border counts as an artificial edge, so no coastal "
            "vignette is drawn along it."))
        self.addParameter(self._h(QgsProcessingParameterBoolean(
            self.WATER_PATTERNS,
            self.tr("Hydrography patterns (coastal vignette, lake hatch, marsh tufts)"),
            False),
            "Classic engraved water textures: parallel coastal vignette "
            "lines along sea shores, hatching inside lakes, tuft symbols "
            "in marshes."))

    def add_sheet_params(self):
        """Sheet decoration + print emulation group (placed in the
        advanced section, labels share common prefixes). Everything is
        off by default."""
        D = QgsProcessingParameterNumber.Double
        self.addParameter(self._h(self._adv(QgsProcessingParameterEnum(
            self.SHEET_FRAME, self.tr("Sheet: frame"),
            options=self.FRAME_OPTS, defaultValue=0)),
            "Decorative frame drawn in the sheet margin. The map border "
            "style adds a narrow checkered band of black-and-white degree "
            "fractions along the outer frame line. Relief displaced "
            "upward overlaps the top frame -- an authentic panoramic-map "
            "effect."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterBoolean(
            self.SHEET_TICKS,
            self.tr("Sheet: graticule ticks with labels (D°MM′)"),
            False)),
            "Latitude/longitude ticks on the frame with labels in degrees "
            "and minutes (grid step 15′ or coarser, so seconds are always "
            "zero and omitted). Works with any CRS via WGS84; at most "
            "three labels per side, overlap-checked."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterBoolean(
            self.SHEET_SCALEBAR,
            self.tr("Sheet: scale bar (old style)"),
            False)),
            "Four alternating black-and-white segments in the lower-left "
            "corner; length rounded to a nice value, computed through "
            "WGS84 so it works with any CRS. Due to the oblique view the "
            "bar is exact along the sheet horizontal."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterEnum(
            self.SHEET_COMPASS,
            self.tr("Sheet: compass rose / north arrow"),
            options=self.COMPASS_OPTS, defaultValue=0)),
            "Cartouche in the upper-right corner pointing to TRUE north "
            "computed from the CRS -- honest on rotated canvases and "
            "converging projections."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterBoolean(
            self.PRINT_DOT,
            self.tr("Print: halftone dot screen under hachures"),
            False)),
            "45-degree halftone dot grid between the fill and the line "
            "work, emulating lithographic printing."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterBoolean(
            self.PRINT_GRAIN, self.tr("Print: paper grain"), False)),
            "Soft irregular noise texture over the whole sheet including "
            "margins (deterministic, no repeating tiles)."))
        self.addParameter(self._h(self._adv(QgsProcessingParameterNumber(
            self.PRINT_MISREG,
            self.tr("Print: color misregistration, px (0 = off; PNG only)"),
            D, 0.0, minValue=0.0, maxValue=4.0)),
            "Old-lithography color misregistration: the red channel of "
            "the finished PNG is shifted right and the blue channel left "
            "by the given amount. Skipped for SVG/PDF output."))

    def sheet_kwargs(self, parameters, context):
        """Sheet/print options dict, or None when everything is off."""
        d = dict(
            frame=self.parameterAsEnum(parameters, self.SHEET_FRAME, context),
            ticks=self.parameterAsBool(parameters, self.SHEET_TICKS, context),
            scalebar=self.parameterAsBool(parameters, self.SHEET_SCALEBAR, context),
            compass=self.parameterAsEnum(parameters, self.SHEET_COMPASS, context),
            dot=self.parameterAsBool(parameters, self.PRINT_DOT, context),
            grain=self.parameterAsBool(parameters, self.PRINT_GRAIN, context),
            misreg=self.parameterAsDouble(parameters, self.PRINT_MISREG, context),
        )
        if (d["frame"] == 0 and d["compass"] == 0
                and not any((d["ticks"], d["scalebar"],
                             d["dot"], d["grain"]))
                and d["misreg"] <= 0.0):
            return None
        return d

    def fill_kwargs(self, parameters, context):
        """Collect fill arguments for the render core. FILL_STYLE:
        0 = none; 1..N = hypsometric with palette N; N+1 = thematic."""
        idx = self.parameterAsEnum(parameters, self.FILL_STYLE, context)
        npal = len(PALETTE_KEYS)
        if idx == 0:
            fmode, pal = "none", PALETTE_KEYS[0]
        elif idx <= npal:
            fmode, pal = "elevation", PALETTE_KEYS[idx - 1]
        else:
            fmode, pal = "thematic", PALETTE_KEYS[0]
        ovr_on = self.parameterAsBool(parameters, self.OVR_ON, context)
        omin = self.parameterAsDouble(parameters, self.OVR_MIN, context) if ovr_on else None
        omax = self.parameterAsDouble(parameters, self.OVR_MAX, context) if ovr_on else None
        paper, ink = self.PAPER_INK[
            self.parameterAsEnum(parameters, self.PAPER_PRESET, context)]
        shade_style = self.parameterAsEnum(parameters, self.SHADE_STYLE, context)
        dens = self.parameterAsDouble(parameters, self.BULK_SHADE, context)
        return dict(
            fill_mode=fmode, palette=pal,
            hypso_shade=self.parameterAsDouble(parameters, self.HYPSO_SHADE, context),
            override_min=omin, override_max=omax,
            stretch=self.parameterAsBool(parameters, self.STRETCH, context),
            fill_alpha=self.parameterAsDouble(parameters, self.FILL_ALPHA, context),
            water_patterns=self.parameterAsBool(parameters, self.WATER_PATTERNS, context),
            bg=paper, ink=ink,
            auto_sea=self.parameterAsBool(parameters, self.AUTO_SEA, context),
            sea_level=self.parameterAsDouble(parameters, self.SEA_LEVEL, context),
            nodata_mode=self.NODATA_KEYS[
                self.parameterAsEnum(parameters, self.NODATA_MODE, context)],
            hand_jitter=self.parameterAsDouble(parameters, self.HAND_JITTER, context),
            bulk_shade=(dens if shade_style == 1 else 0.0),
            bulk_win=self.parameterAsInt(parameters, self.BULK_WIN, context),
            anag=(dens if shade_style == 2 else 0.0),
            anag_spacing=self.parameterAsInt(parameters, self.ANAG_SPACING, context),
        )

    def build_overlays(self, parameters, context, dem_crs, grid, fill_mode,
                       feedback=None):
        """Extract all optional vector layers into plain geometry dicts,
        reprojected to the DEM CRS and clipped to the working extent."""
        from . import overlays as ov

        def gv(p):
            return self.parameterAsVectorLayer(parameters, p, context)

        ext = grid.extent
        o = {}
        o["river"] = ov.extract_lines(gv(self.RIVERS), dem_crs, ext)
        o["road"] = ov.extract_lines(gv(self.ROADS), dem_crs, ext)
        o["lake"] = ov.extract_polys(gv(self.LAKES), dem_crs, ext)
        o["sea"] = ov.extract_polys(gv(self.SEAS), dem_crs, ext)
        o["marsh"] = ov.extract_polys(gv(self.MARSHES), dem_crs, ext)
        o["settle_poly"] = ov.extract_polys(gv(self.SETTLE_POLY), dem_crs, ext)
        lbl = self.parameterAsString(parameters, self.SETTLE_LABEL, context)
        o["settle_pt"] = ov.extract_points(gv(self.SETTLE_PT), dem_crs, lbl, ext)
        if fill_mode == "thematic":
            o["thematic"] = ov.extract_thematic(gv(self.THEMATIC), dem_crs, ext)
            if feedback and not o["thematic"]:
                feedback.pushWarning(self.tr(
                    "Thematic fill selected, but the layer is empty or missing."))

        o["forest"] = ov.extract_polys(gv(self.LC_FOREST), dem_crs, ext)
        o["sand"] = ov.extract_polys(gv(self.LC_SAND), dem_crs, ext)
        o["ice"] = ov.extract_polys(gv(self.LC_ICE), dem_crs, ext)
        o["scrub"] = ov.extract_polys(gv(self.LC_SCRUB), dem_crs, ext)
        o["grass"] = ov.extract_polys(gv(self.LC_GRASS), dem_crs, ext)
        return o

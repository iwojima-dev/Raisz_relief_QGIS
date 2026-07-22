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
"""Hybrid algorithm: "Landform map (Hammond + Mower + Alpha)"."""

from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterRasterLayer, QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean, QgsProcessingParameterEnum,
    QgsProcessingParameterFileDestination,
)

from ._base import ReliefAlgorithmBase, NUM_DOUBLE as D, NUM_INT as I


class PhysiographicAlgorithm(ReliefAlgorithmBase):
    DEM = "DEM"
    INTERVAL = "INTERVAL"; VERT_EXAG = "VERT_EXAG"; VIEW_ANGLE = "VIEW_ANGLE"
    BASE_SCALE = "BASE_SCALE"; SMOOTH = "SMOOTH"
    HAMMOND_WINDOW = "HAMMOND_WINDOW"; PLAIN_LO = "PLAIN_LO"; PLAIN_HI = "PLAIN_HI"
    HAMMOND_MODE = "HAMMOND_MODE"; PLAIN_MID = "PLAIN_MID"; PLAIN_WIDTH = "PLAIN_WIDTH"
    HAMMOND_CLASS = "HAMMOND_CLASS"
    HAMMOND_P_LO = "HAMMOND_P_LO"
    HAMMOND_P_HI = "HAMMOND_P_HI"

    HAMMOND_MODES = ["Manual: two thresholds (m)",
                     "Manual: midpoint + width (m)",
                     "Hammond classes", "Auto from DEM (draft)"]
    HAMMOND_CLASSES = ["<=30 m -- plains", "<=90 m -- hills/low mountains",
                       "<=150 m -- mountains", "<=300 m -- high mountains"]
    HAMMOND_CLASS_MID = [30.0, 90.0, 150.0, 300.0]
    VIEW_AZIMUTH = "VIEW_AZIMUTH"
    REL_SCALE = "REL_SCALE"; REL_TARGET = "REL_TARGET"
    REL_LEVELS = "REL_LEVELS"; REL_SLOPES = "REL_SLOPES"
    VIEW_AZIMUTHS = ["No rotation (north up)", "90° counter-clockwise",
                     "180° (view from the opposite side)", "90° clockwise"]
    LIGHT_AZ = "LIGHT_AZ"; LIGHT_ALT = "LIGHT_ALT"
    MAX_WIDTH = "MAX_WIDTH"; SLOPE_WEIGHT = "SLOPE_WEIGHT"
    MIN_DRAW_WIDTH = "MIN_DRAW_WIDTH"; FALL_SPACING = "FALL_SPACING"
    STIPPLE_R = "STIPPLE_R"; DOT_SIZE = "DOT_SIZE"; MAX_PX = "MAX_PX"
    DRAW_FALL = "DRAW_FALL"; DRAW_STIPPLE = "DRAW_STIPPLE"
    DRAW_FRAMEWORK = "DRAW_FRAMEWORK"; FRAMEWORK_ON_PLAINS = "FRAMEWORK_ON_PLAINS"
    DRAW_BASELINE = "DRAW_BASELINE"; VALLEY_DENSIFY = "VALLEY_DENSIFY"
    DENSIFY_SCALE = "DENSIFY_SCALE"; DPI = "DPI"; OUTPUT = "OUTPUT"

    def createInstance(self):
        return PhysiographicAlgorithm()

    def name(self):
        return "landform"

    def displayName(self):
        return self.tr("Landform map (Hammond + Mower + Alpha)")

    def shortHelpString(self):
        return self.tr(
            "Hybrid physiographic map from a DEM: Hammond classification "
            "(mountains hachured, plains stippled) with Mower-style "
            "generalization and Ridd oblique volume. Decoration layer: "
            "hypsometric fill (Patterson/Bartholomew/Peucker/Imhof, absolute "
            "elevations) or thematic fill (colors from the layer style), "
            "draped over the displaced relief; rivers, lakes, seas, marshes, "
            "roads and settlements as separate layers, monochrome on sepia; "
            "all layers clipped to the DEM extent. Sheet decoration and "
            "old-print emulation included. Presentation graphics output "
            "(PNG/SVG/PDF)."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.DEM, self.tr("Digital elevation model (DEM)")))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.INTERVAL, self.tr("Contour interval, m"), D, 40.0,
            minValue=0.5),
            "Vertical spacing of the invisible contour levels the hachures "
            "hang from."))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.VERT_EXAG, self.tr("Vertical exaggeration"), D, 2.2,
            minValue=0.2, maxValue=10.0),
            "Scales the northward displacement of the relief: the higher "
            "the mountain, the taller its oblique profile."))
        self.addParameter(self._h(QgsProcessingParameterEnum(
            self.VIEW_AZIMUTH, self.tr("View azimuth (canvas rotation)"),
            options=self.VIEW_AZIMUTHS, defaultValue=0),
            "Rotates the whole canvas so the relief is viewed from another "
            "side."))
        self.addParameter(self._h(QgsProcessingParameterBoolean(
            self.REL_SCALE,
            self.tr("Relative scene scale (displacement and belts from the "
                    "scene range, not absolute meters)"), False),
            "Turn this on for gentle scenes -- low hills or steep but low "
            "coastal cliffs. The displacement is normalized so that the "
            "p99 of the relief reaches the target percentage of the sheet "
            "height, and the contour interval is derived from the number "
            "of belts instead of absolute meters. Hammond classification "
            "is not affected. Default behavior is unchanged when off."))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.REL_TARGET,
            self.tr("Relative mode: target relief height, % of sheet height "
                    "(exaggeration acts as a multiplier, 1.0 = exact target)"),
            D, 12.0, minValue=2.0, maxValue=60.0),
            "How tall the relief should stand on the sheet. In relative "
            "mode set Vertical exaggeration to about 1.0 -- the default "
            "2.2 comes from absolute mode and would double the target."))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.REL_LEVELS,
            self.tr("Relative mode: number of elevation belts (instead of "
                    "the interval in m)"),
            I, 12, minValue=2, maxValue=60),
            "The contour interval becomes (zmax - zmin) / N. Affects both "
            "the framework and the fall-line length."))
        self.addParameter(self._h(QgsProcessingParameterBoolean(
            self.REL_SLOPES,
            self.tr("Relative slopes (scene percentiles instead of absolute "
                    "degrees; full line work on gentle scenes)"), False),
            "Slope ratio is normalized by the p95 of the tangent inside "
            "the relief zone. Hammond classification is computed from "
            "local relief upstream and stays untouched. The price: stroke "
            "weight is no longer comparable between sheets."))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.HAMMOND_WINDOW, self.tr("Hammond classification window, m"),
            D, 3000.0, minValue=200.0),
            "Size of the moving window (in map units) over which the local "
            "relief range is measured for the plains/mountains split."))
        self.addParameter(self._h(QgsProcessingParameterEnum(
            self.HAMMOND_MODE, self.tr("Classification: plains threshold mode"),
            options=self.HAMMOND_MODES, defaultValue=1),
            "How the plains/mountains thresholds are set: two explicit "
            "values, a midpoint with a transition width, canonical Hammond "
            "classes, or automatic percentiles of the DEM (draft)."))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.PLAIN_MID,
            self.tr("Midpoint: local relief at the plains/relief boundary, m"),
            D, 90.0, minValue=5.0),
            "Used in 'midpoint + width' mode."))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.PLAIN_WIDTH, self.tr("Transition width, +/- % of midpoint"),
            D, 50.0, minValue=5.0, maxValue=95.0),
            "Half-width of the fuzzy plains-to-mountains transition."))
        self.addParameter(QgsProcessingParameterEnum(
            self.HAMMOND_CLASS, self.tr("Hammond class (for 'classes' mode)"),
            options=self.HAMMOND_CLASSES, defaultValue=1))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.STIPPLE_R, self.tr("Plains dot spacing, px (smaller = denser)"),
            D, 4.0, minValue=1.5, maxValue=30.0),
            "Spacing of the jittered stipple grid on plains."))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.MAX_PX, self.tr("Working resolution (max side, px)"),
            I, 2000, minValue=400, maxValue=6000),
            "The DEM is resampled so its longer side does not exceed this. "
            "Higher values give finer detail at the cost of speed and "
            "memory."))

        # fill and decoration layers (from the base class)
        self.add_fill_params()
        self.add_overlay_params()
        self.add_sheet_params()

        self.addParameter(QgsProcessingParameterBoolean(
            self.DRAW_FALL, self.tr("Draw mountains (fall lines)"), True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.DRAW_STIPPLE, self.tr("Draw plains (stipple)"), True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.DRAW_FRAMEWORK, self.tr("Draw contour framework"), True))
        self.addParameter(self._h(QgsProcessingParameterBoolean(
            self.VALLEY_DENSIFY, self.tr("Densify valley dots toward mountains"),
            True),
            "Stipple gets denser as it approaches mountain fronts, "
            "following the classic manner."))
        self.addParameter(self._h(QgsProcessingParameterBoolean(
            self.DRAW_BASELINE, self.tr("Outline mountain feet (dotted)"),
            True),
            "A dotted baseline separating hachured mountains from stippled "
            "plains."))

        # advanced
        adv = [
            (self.VIEW_ANGLE, "View angle above horizon, deg", D, 40.0,
             "Oblique viewing angle; lower angle -> stronger displacement."),
            (self.BASE_SCALE, "Local basis radius, px", I, 55,
             "Radius of the local smoothing basis for stroke direction."),
            (self.SMOOTH, "Surface smoothing, px", D, 1.6,
             "Gaussian pre-smoothing of the DEM."),
            (self.PLAIN_LO, "Two thresholds: below = plain, m (mode A)", D, 30.0,
             "Lower threshold of the manual two-threshold mode."),
            (self.PLAIN_HI, "Two thresholds: above = relief, m (mode A)", D, 90.0,
             "Upper threshold of the manual two-threshold mode."),
            (self.HAMMOND_P_LO, "Auto: lower percentile, % ('auto' mode)", D, 40.0,
             "Lower percentile of local relief for the draft auto mode."),
            (self.HAMMOND_P_HI, "Auto: upper percentile, % ('auto' mode)", D, 85.0,
             "Upper percentile of local relief for the draft auto mode."),
            (self.LIGHT_AZ, "Light azimuth, deg", D, 315.0,
             "Direction the light comes from (0 = north, clockwise)."),
            (self.LIGHT_ALT, "Light altitude, deg", D, 45.0,
             "Elevation of the light source above the horizon."),
            (self.MAX_WIDTH, "Max stroke width, pt", D, 1.9,
             "Upper limit of the light-modulated stroke width."),
            (self.SLOPE_WEIGHT, "Slope weight vs light (0-1)", D, 0.45,
             "Balance between slope steepness and illumination in the "
             "stroke width."),
            (self.MIN_DRAW_WIDTH, "Cutoff: thinner is not drawn, pt", D, 0.35,
             "Strokes thinner than this are dropped entirely."),
            (self.FALL_SPACING, "Base fall-line spacing, px", D, 4.0,
             "Horizontal spacing between neighboring strokes."),
            (self.DOT_SIZE, "Dot size", D, 0.8,
             "Marker size of the plains stipple."),
            (self.DENSIFY_SCALE, "Dot densification distance near mountains, m",
             D, 2500.0,
             "Distance over which valley stipple densifies toward "
             "mountain fronts."),
            (self.DPI, "Raster DPI", I, 150,
             "Resolution of the output image."),
        ]
        for nm, lbl, typ, dv, hlp in adv:
            self.addParameter(self._h(self._adv(QgsProcessingParameterNumber(
                nm, self.tr(lbl), typ, dv)), hlp))
        self.addParameter(self._adv(QgsProcessingParameterBoolean(
            self.FRAMEWORK_ON_PLAINS, self.tr("Framework on plains too"),
            False)))

        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT, self.tr("Landform map (PNG/SVG/PDF)"),
            fileFilter="PNG (*.png);;SVG (*.svg);;PDF (*.pdf)"))

    def processAlgorithm(self, parameters, context, feedback):
        try:
            import numpy, scipy, matplotlib, rasterio  # noqa
        except Exception as e:
            raise QgsProcessingException(self.tr(
                "Missing dependencies (numpy/scipy/matplotlib/rasterio): ")
                + repr(e))

        dem = self.parameterAsRasterLayer(parameters, self.DEM, context)
        if dem is None or not dem.isValid():
            raise QgsProcessingException(self.tr("No valid DEM provided."))
        if dem.crs().isGeographic():
            feedback.pushWarning(self.tr(
                "DEM is in degrees. A metric projection (e.g. UTM) is "
                "recommended."))
        dem_path = dem.source().split("|")[0]
        out_png = self.parameterAsFileOutput(parameters, self.OUTPUT, context)

        def gd(p): return self.parameterAsDouble(parameters, p, context)
        def gi(p): return self.parameterAsInt(parameters, p, context)
        def gb(p): return self.parameterAsBool(parameters, p, context)

        from . import grid as gridmod
        from . import physio_core as pc

        grid = gridmod.working_grid(dem_path, max_px=gi(self.MAX_PX))
        fk = self.fill_kwargs(parameters, context)
        feedback.pushInfo(self.tr("Extracting and clipping overlay layers..."))
        overlays = self.build_overlays(parameters, context, dem.crs(), grid,
                                       fk["fill_mode"], feedback)

        def progress(p, msg):
            feedback.setProgress(int(p)); feedback.pushInfo(msg)
            if feedback.isCanceled():
                raise QgsProcessingException(self.tr("Canceled."))

        # plains threshold mode A/B/C/E -> (plain_lo, plain_hi, auto)
        hmode = self.parameterAsEnum(parameters, self.HAMMOND_MODE, context)
        h_auto = False
        p_lo, p_hi = gd(self.PLAIN_LO), gd(self.PLAIN_HI)
        if hmode == 1:        # midpoint + width
            mid = gd(self.PLAIN_MID); w = gd(self.PLAIN_WIDTH) / 100.0
            p_lo, p_hi = mid * (1.0 - w), mid * (1.0 + w)
        elif hmode == 2:      # Hammond classes
            mid = self.HAMMOND_CLASS_MID[
                self.parameterAsEnum(parameters, self.HAMMOND_CLASS, context)]
            p_lo, p_hi = mid * 0.5, mid * 1.5
        elif hmode == 3:      # auto from DEM (draft)
            h_auto = True
        feedback.pushInfo(self.tr("Plains threshold mode: ")
                          + self.HAMMOND_MODES[hmode])

        feedback.pushInfo(self.tr("Rendering the landform map..."))
        stats = pc.render_landform(
            dem_path, out_png, grid=grid,
            interval=gd(self.INTERVAL), view_angle=gd(self.VIEW_ANGLE),
            vert_exag=gd(self.VERT_EXAG), base_scale_px=gi(self.BASE_SCALE),
            view_rot=self.parameterAsEnum(parameters, self.VIEW_AZIMUTH, context),
            light_az=gd(self.LIGHT_AZ), light_alt=gd(self.LIGHT_ALT),
            smooth_sigma_px=gd(self.SMOOTH),
            hammond_window_m=gd(self.HAMMOND_WINDOW),
            plain_lo=p_lo, plain_hi=p_hi, hammond_auto=h_auto,
            hammond_p_lo=gd(self.HAMMOND_P_LO), hammond_p_hi=gd(self.HAMMOND_P_HI),
            max_width=gd(self.MAX_WIDTH), slope_weight=gd(self.SLOPE_WEIGHT),
            min_draw_width=gd(self.MIN_DRAW_WIDTH), fall_spacing=gd(self.FALL_SPACING),
            stipple_r_px=gd(self.STIPPLE_R), dot_size=gd(self.DOT_SIZE),
            draw_framework=gb(self.DRAW_FRAMEWORK),
            framework_on_plains=gb(self.FRAMEWORK_ON_PLAINS),
            draw_fall=gb(self.DRAW_FALL), draw_stipple=gb(self.DRAW_STIPPLE),
            draw_baseline=gb(self.DRAW_BASELINE),
            valley_densify=gb(self.VALLEY_DENSIFY),
            densify_scale_m=gd(self.DENSIFY_SCALE),
            overlays=overlays, sheet=self.sheet_kwargs(parameters, context),
            rel_scale=gb(self.REL_SCALE), rel_target=gd(self.REL_TARGET),
            rel_levels=gi(self.REL_LEVELS), rel_slopes=gb(self.REL_SLOPES),
            dpi=gi(self.DPI), progress=progress, **fk)

        feedback.pushInfo(self.tr(
            f"Done: {stats['cols']}x{stats['rows']}, dots {stats['stipple']}, "
            f"fall {stats['fall_segs']}, rivers {stats.get('river')}, "
            f"roads {stats.get('road')}, plains {stats['plain_frac']*100:.0f}% "
            f"(thresholds {stats.get('plain_lo',0):.0f}/"
            f"{stats.get('plain_hi',0):.0f} m)."))
        return {self.OUTPUT: out_png}

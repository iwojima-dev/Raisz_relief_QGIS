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
"""Classic algorithm: "Classic physiographic (full resolution)"."""

from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterRasterLayer, QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean, QgsProcessingParameterEnum,
    QgsProcessingParameterFileDestination,
)

from ._base import ReliefAlgorithmBase, NUM_DOUBLE as D, NUM_INT as I


class ClassicAlgorithm(ReliefAlgorithmBase):
    DEM = "DEM"
    INTERVAL = "INTERVAL"; VERT_EXAG = "VERT_EXAG"; VIEW_ANGLE = "VIEW_ANGLE"
    BASE_SCALE = "BASE_SCALE"; LIGHT_AZ = "LIGHT_AZ"; LIGHT_ALT = "LIGHT_ALT"
    FALL_SPACING = "FALL_SPACING"; SHADOW_DENSITY = "SHADOW_DENSITY"
    LIGHT_SKIP = "LIGHT_SKIP"; MIN_SLOPE = "MIN_SLOPE"
    DRAW_FALL = "DRAW_FALL"; DRAW_FRAMEWORK = "DRAW_FRAMEWORK"
    MEM_LIMIT = "MEM_LIMIT"; DPI = "DPI"; OUTPUT = "OUTPUT"
    STRIP_ROWS = "STRIP_ROWS"
    REL_SCALE = "REL_SCALE"; REL_TARGET = "REL_TARGET"
    REL_LEVELS = "REL_LEVELS"; REL_SLOPES = "REL_SLOPES"
    VIEW_AZIMUTH = "VIEW_AZIMUTH"
    VIEW_AZIMUTHS = ["No rotation (north up)", "90° counter-clockwise",
                     "180° (view from the opposite side)", "90° clockwise"]

    def createInstance(self):
        return ClassicAlgorithm()

    def name(self):
        return "classic"

    def displayName(self):
        return self.tr("Classic physiographic (full resolution)")

    def shortHelpString(self):
        return self.tr(
            "Classic physiographic method (Alpha & Winter; Raisz; Ridd) at "
            "the FULL resolution of the DEM: uniform engraved hachuring over "
            "the entire surface, without Hammond classification or stippled "
            "plains -- the striking original look. The same decoration is "
            "available as in the hybrid (fill, waters, roads, settlements, "
            "sheet decoration, print emulation). Very large DEMs may exhaust "
            "memory -- set the limit; when exceeded, strip tiling is enabled "
            "automatically or the algorithm stops with a warning. "
            "Presentation graphics output (PNG/SVG/PDF)."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.DEM, self.tr("Digital elevation model (DEM)")))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.INTERVAL, self.tr("Contour interval, m"), D, 40.0,
            minValue=0.5),
            "Vertical spacing of the invisible contour levels the hachures "
            "hang from. Smaller interval -> denser rows of strokes."))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.VERT_EXAG, self.tr("Vertical exaggeration"), D, 2.2,
            minValue=0.2, maxValue=10.0),
            "Scales the northward displacement of the relief: the higher "
            "the mountain, the taller its oblique profile."))
        self.addParameter(self._h(QgsProcessingParameterEnum(
            self.VIEW_AZIMUTH, self.tr("View azimuth (canvas rotation)"),
            options=self.VIEW_AZIMUTHS, defaultValue=0),
            "Rotates the whole canvas so the relief is viewed from another "
            "side. Graticule ticks and the compass rose follow the "
            "rotation."))
        self.addParameter(self._h(QgsProcessingParameterBoolean(
            self.REL_SCALE,
            self.tr("Relative scene scale (displacement and belts from the "
                    "scene range, not absolute meters)"), False),
            "Turn this on for gentle scenes -- low hills or steep but low "
            "coastal cliffs. The displacement is normalized so that the "
            "p99 of the relief reaches the target percentage of the sheet "
            "height, and the contour interval is derived from the number "
            "of belts instead of absolute meters. Default behavior is "
            "unchanged when off."))
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
            self.tr("Relative slopes (scene percentiles instead of 4°/45°; "
                    "full line work on gentle scenes)"), False),
            "Stroke cutoff and full graphic range are taken from scene "
            "percentiles (p30/p95) rather than fixed degrees. The price: "
            "stroke weight is no longer comparable between sheets."))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.MEM_LIMIT, self.tr("Memory limit, GB (crash guard)"),
            D, 8.0, minValue=0.5, maxValue=256.0),
            "Estimated memory above this limit triggers automatic strip "
            "tiling instead of a crash."))
        self.addParameter(self._h(QgsProcessingParameterNumber(
            self.STRIP_ROWS,
            self.tr("Strips: strip height, rows (0 = no strips)"),
            I, 0, minValue=0),
            "Manual strip tiling for huge sheets: the DEM is processed in "
            "horizontal strips of this height. 0 = single pass (strips "
            "still auto-enable if the memory limit is exceeded)."))

        self.add_fill_params()
        self.add_overlay_params()
        self.add_sheet_params()

        self.addParameter(self._h(QgsProcessingParameterBoolean(
            self.DRAW_FALL, self.tr("Draw hachures (fall lines)"), True),
            "The main engraved strokes running downslope. Disable to keep "
            "only the contour framework (or the anaglyptography texture)."))
        self.addParameter(self._h(QgsProcessingParameterBoolean(
            self.DRAW_FRAMEWORK, self.tr("Draw contour framework"), True),
            "Thin displaced contour lines forming the skeleton of the "
            "oblique view."))

        adv = [
            (self.VIEW_ANGLE, "View angle above horizon, deg", D, 40.0,
             "Oblique viewing angle; lower angle -> stronger displacement."),
            (self.BASE_SCALE, "Local basis radius, px", I, 55,
             "Radius of the local smoothing basis used for stroke "
             "direction; larger radius -> calmer strokes."),
            (self.LIGHT_AZ, "Light azimuth, deg", D, 315.0,
             "Direction the light comes from (0 = north, clockwise). "
             "Shared by hachure density, hillshade blend and large-form "
             "shading."),
            (self.LIGHT_ALT, "Light altitude, deg", D, 45.0,
             "Elevation of the light source above the horizon."),
            (self.FALL_SPACING, "Base fall-line spacing, px", D, 4.0,
             "Horizontal spacing between neighboring strokes before "
             "light modulation."),
            (self.SHADOW_DENSITY, "Stroke densification in shade (0-1)", D, 0.8,
             "How much denser the strokes get on shaded slopes."),
            (self.LIGHT_SKIP, "Light threshold: brighter -> skip (0-1)", D, 0.75,
             "Strokes are dropped where illumination exceeds this "
             "threshold, leaving lit slopes blank."),
            (self.MIN_SLOPE, "Min slope for a stroke, deg", D, 4.0,
             "Slopes gentler than this get no hachures."),
            (self.DPI, "Raster DPI", I, 150,
             "Resolution of the output image. Also affects the "
             "rasterization of embedded fills in SVG/PDF."),
        ]
        for nm, lbl, typ, dv, hlp in adv:
            self.addParameter(self._h(self._adv(QgsProcessingParameterNumber(
                nm, self.tr(lbl), typ, dv)), hlp))

        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT, self.tr("Classic map (PNG/SVG/PDF)"),
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
        dem_path = dem.source().split("|")[0]
        out_png = self.parameterAsFileOutput(parameters, self.OUTPUT, context)

        def gd(p): return self.parameterAsDouble(parameters, p, context)
        def gi(p): return self.parameterAsInt(parameters, p, context)
        def gb(p): return self.parameterAsBool(parameters, p, context)

        from . import grid as gridmod
        from . import classic_core as cc

        grid = gridmod.working_grid(dem_path, max_px=None)   # full resolution
        dpi = gi(self.DPI)
        strip_rows = gi(self.STRIP_ROWS)
        mem = gridmod.estimate_memory_gb(grid, dpi)
        limit = gd(self.MEM_LIMIT)
        feedback.pushInfo(self.tr(
            f"Full resolution {grid.nx}x{grid.ny}, estimated memory "
            f"~{mem:.2f} GB (limit {limit:.1f} GB)."))

        fk = self.fill_kwargs(parameters, context)
        sk = self.sheet_kwargs(parameters, context)
        rel = dict(rel_scale=gb(self.REL_SCALE), rel_target=gd(self.REL_TARGET),
                   rel_levels=gi(self.REL_LEVELS), rel_slopes=gb(self.REL_SLOPES))

        def progress(p, msg):
            feedback.setProgress(int(p)); feedback.pushInfo(msg)
            if feedback.isCanceled():
                raise QgsProcessingException(self.tr("Canceled."))

        # auto-enable strips when the memory estimate exceeds the limit
        if strip_rows == 0 and mem > limit:
            per_row = max(grid.nx * 8 * 12, 1)
            strip_rows = max(512, int(limit * 0.4 * 1e9 / per_row))
            feedback.pushWarning(self.tr(
                "Memory estimate %.2f GB > limit %.1f GB -- auto strips "
                "enabled (%d rows/strip)." % (mem, limit, strip_rows)))

        # -- strip mode (large sheets without memory overflow) --
        if strip_rows > 0:
            from . import classic_striped as cs
            feedback.pushWarning(self.tr(
                "Strip mode (%d rows/strip). View rotation is not yet "
                "applied in strips." % strip_rows))
            feedback.pushInfo(self.tr("Extracting and clipping overlay layers..."))
            overlays = self.build_overlays(parameters, context, dem.crs(),
                                           grid, fk["fill_mode"], feedback)
            stats = cs.render_classic_striped(
                dem_path, out_png, grid=grid,
                interval=gd(self.INTERVAL), view_angle=gd(self.VIEW_ANGLE),
                vert_exag=gd(self.VERT_EXAG), base_scale_px=gi(self.BASE_SCALE),
                light_az=gd(self.LIGHT_AZ), light_alt=gd(self.LIGHT_ALT),
                fall_spacing=gd(self.FALL_SPACING),
                shadow_density=gd(self.SHADOW_DENSITY),
                light_skip=gd(self.LIGHT_SKIP), min_slope_deg=gd(self.MIN_SLOPE),
                draw_framework=gb(self.DRAW_FRAMEWORK), draw_fall=gb(self.DRAW_FALL),
                fill_mode=fk["fill_mode"], palette=fk["palette"],
                hypso_shade=fk["hypso_shade"], override_min=fk["override_min"],
                override_max=fk["override_max"], stretch=fk["stretch"],
                fill_alpha=fk["fill_alpha"], ink=fk["ink"], bg=fk["bg"],
                hand_jitter=fk["hand_jitter"], overlays=overlays,
                water_patterns=fk["water_patterns"], auto_sea=fk["auto_sea"],
                sea_level=fk["sea_level"], sheet=sk,
                nodata_mode=fk["nodata_mode"],
                settle_font=fk["settle_font"],
                settle_font_scale=fk["settle_font_scale"],
                bulk_shade=fk["bulk_shade"], bulk_win=fk["bulk_win"],
                anag=fk["anag"], anag_spacing=fk["anag_spacing"], **rel,
                strip_rows=strip_rows, dpi=dpi, progress=progress)
            feedback.pushInfo(self.tr(
                "Done (strips): %dx%d, %d strips, %d fall segments."
                % (stats["cols"], stats["rows"], stats["strips"],
                   stats["fall_segs"])))
            return {self.OUTPUT: out_png}

        if mem > limit:
            raise QgsProcessingException(self.tr(
                f"Memory estimate {mem:.2f} GB exceeds the limit "
                f"{limit:.1f} GB. Enable strip mode (strip height > 0), "
                "raise the limit, lower the DPI, or use the landform "
                "algorithm."))

        feedback.pushInfo(self.tr("Extracting and clipping overlay layers..."))
        overlays = self.build_overlays(parameters, context, dem.crs(), grid,
                                       fk["fill_mode"], feedback)

        feedback.pushInfo(self.tr("Rendering the classic map..."))
        stats = cc.render_classic(
            dem_path, out_png, grid=grid,
            interval=gd(self.INTERVAL), view_angle=gd(self.VIEW_ANGLE),
            vert_exag=gd(self.VERT_EXAG), base_scale_px=gi(self.BASE_SCALE),
            view_rot=self.parameterAsEnum(parameters, self.VIEW_AZIMUTH, context),
            light_az=gd(self.LIGHT_AZ), light_alt=gd(self.LIGHT_ALT),
            fall_spacing=gd(self.FALL_SPACING),
            shadow_density=gd(self.SHADOW_DENSITY), light_skip=gd(self.LIGHT_SKIP),
            min_slope_deg=gd(self.MIN_SLOPE),
            draw_framework=gb(self.DRAW_FRAMEWORK), draw_fall=gb(self.DRAW_FALL),
            overlays=overlays, sheet=sk, dpi=dpi, progress=progress,
            **rel, **fk)
        feedback.pushInfo(self.tr(
            f"Done: {stats['cols']}x{stats['rows']}, fall {stats['fall_segs']}, "
            f"rivers {stats.get('river')}, roads {stats.get('road')}."))
        return {self.OUTPUT: out_png}

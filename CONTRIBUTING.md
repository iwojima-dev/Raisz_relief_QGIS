# Contributing

Thanks for your interest in the plugin. Bug reports, cartographic
critique and pull requests are all welcome.

## Reporting bugs

Open an issue and include:

- QGIS version and operating system
- Which algorithm you ran (Landform or Classic)
- DEM size, CRS and approximate elevation range of the scene
- The full log (it records every computed coefficient) — the log pane of
  the plugin window, or the Processing log if you ran it from there
- The parameter values you used, or the saved Processing preset

A screenshot of the wrong result is worth a lot — this is a plugin about
appearance, so "it looks wrong" is a legitimate bug report. Please say
what you expected it to look like.

## Suggesting cartographic features

This plugin follows a specific historical manner. When proposing a new
graphic technique, it helps to point at a real map or a published
description of the technique rather than only at a desired effect.

## Pull requests

- Keep the existing code style: 4 spaces, ~79-column lines, docstrings
  and comments in English.
- Every source file carries the GPL v3 header. New files need it too.
- Vectorize with numpy where you can; the cores run over millions of
  pixels and Python loops are the usual bottleneck.
- Anything drawn on the sheet must respect the paper/ink preset — take
  colors from `theme.resolve()` rather than hard-coding them.
- New drawing code has to work in three places: `classic_core`,
  `physio_core` and `classic_striped`. In strip mode, per-scene
  coefficients must be computed once on the downsampled pass and passed
  into the strips, or the strips will disagree at the seams.
- A new parameter is declared once, in the algorithm (or `_base.py`).
  The plugin window builds its fields from the algorithm's own parameter
  definitions, so labels, defaults and ranges never need repeating. Only
  its tab is chosen by hand, in `gui/layout.py`; a parameter missing
  from that file still appears, in an "Other" tab, so add it to the
  right box rather than leaving it there. If the parameter is read only
  under some setting, add a rule to `DEPENDENCIES` in the same file so
  the window greys it out otherwise.
- A built-in preset is a claim about how a kind of relief should look,
  so add or change one only with test renders of a real DEM of that
  kind, and name the DEM in the comment above `BUILTIN` in
  `gui/presets.py`. Give resolution-dependent values in ground units
  (`BASE_SCALE_M`, `BENCH_PX`), never in pixels.
- Thresholds that must survive a change of data source belong in units
  that do not depend on resolution. The plugin is used with open DEMs at
  30 m, 90 m and coarser, where the contour interval grows with the
  pixel: a threshold stated in pixels or metres will miss.
- Every text the user sees goes through translation. Use `tr()` (or
  `self.tr()` in an algorithm) on the template and format afterwards:
  `tr("Strip %d/%d...") % (i, n)`, never `tr("..." % x)` and never an
  f-string — a formatted string does not match the catalogue. Lists
  built at import time (option lists, tab titles) are marked with `N_()`
  and translated where they are shown. Parameter labels and help passed
  to `_h()`, `_vec()` and the parameter tables are picked up as they
  are. Internal diagnostics for the QGIS message log may stay English.
- After changing texts run `python tools/update_translations.py`: it
  adds new strings to `raisz_relief/i18n/raisz_relief_ru.ts` as
  unfinished and keeps existing translations. Translate them (Qt
  Linguist or a text editor), then compile with
  `lrelease raisz_relief/i18n/raisz_relief_ru.ts`. Commit both the
  `.ts` and the `.qm`. An untranslated string simply shows in English.
- Use the scoped enum forms everywhere: `QgsProcessingGui.WidgetType.
  Standard`, `QgsProcessingParameterDefinition.Flag.Advanced`,
  `QgsProcessingParameterNumber.Type.Double`, `Qt.Orientation.Vertical`.
  The unscoped spellings work on Qt5 but the repository's Qt6
  compatibility check rejects them. `algorithms/_base.py` and
  `gui/relief_dialog.py` define short aliases at the top; reuse them
  rather than spelling the enum out again.
- A literal percent sign in `metadata.txt` must be doubled (`5%%`). The
  file is read by `configparser`, where a single `%` starts an
  interpolation and the whole plugin fails to parse.
- Check that the file still compiles: `python -m py_compile <file>`.
- Test with at least one gentle scene and one mountainous scene, and with
  strip mode enabled if you touched the classic core.

## Project layout

```
raisz_relief/
  plugin.py                     toolbar buttons, Raster menu, provider
  provider.py                   Processing provider
  i18n/
    __init__.py                 tr(), N_(), translator for the QGIS language
    raisz_relief_ru.ts / .qm    Russian translation (source / compiled)
  gui/
    relief_dialog.py            the plugin window: tabs, background run
    layout.py                   which parameter goes in which tab, and
                                which settings grey out which fields
    analyze.py                  "Analyze DEM": statistics, suggested interval
    presets.py                  relief presets: built-in table, user presets
  algorithms/
    _base.py                    shared parameters, tooltips, overlay extraction
    classic_algorithm.py        Classic physiographic (Processing algorithm)
    physiographic_algorithm.py  Landform map (Processing algorithm)
    classic_core.py             classic render core
    classic_striped.py          classic core, strip tiling
    physio_core.py              hybrid render core
    grid.py                     working grid, DEM reading, relative scaling
    fills.py                    fill pipeline and draping
    palettes.py                 hypsometric palettes
    theme.py                    symbology per background
    compose.py                  overlay drawing primitives
    overlays.py                 vector extraction (QGIS side)
    patterns.py                 hydrography and land cover textures
    watercolor.py               watercolour styling of the fill
    sheet.py                    frames, graticule, scale bar, compass
    print_fx.py                 dot screen, grain, misregistration
    engrave.py                  anaglyptography
```

Outside the plugin folder, `tools/update_translations.py` keeps the
translation sources in step with the code.

## License

By contributing you agree that your work is licensed under the GNU
General Public License v3.0 or later, like the rest of the project.

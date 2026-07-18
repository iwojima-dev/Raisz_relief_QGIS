# Contributing

Thanks for your interest in the plugin. Bug reports, cartographic
critique and pull requests are all welcome.

## Reporting bugs

Open an issue and include:

- QGIS version and operating system
- Which algorithm you ran (Landform or Classic)
- DEM size, CRS and approximate elevation range of the scene
- The full Processing log (it records every computed coefficient)
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
- Check that the file still compiles: `python -m py_compile <file>`.
- Test with at least one gentle scene and one mountainous scene, and with
  strip mode enabled if you touched the classic core.

## Project layout

```
raisz_relief/
  plugin.py, provider.py        QGIS registration
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
    sheet.py                    frames, graticule, scale bar, compass
    print_fx.py                 dot screen, grain, misregistration
    engrave.py                  anaglyptography
```

## License

By contributing you agree that your work is licensed under the GNU
General Public License v3.0 or later, like the rest of the project.

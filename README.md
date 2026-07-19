# Raisz-style Relief

A QGIS Processing plugin that turns a DEM into presentation-quality
physiographic relief graphics in the manner of **Erwin Raisz** — oblique
hachured mountains, stippled plains, engraved waters and a decorated map
sheet. The output is a *picture*, not a georeferenced raster: PNG, SVG or
PDF ready for print or for editing in vector software.

![License](https://img.shields.io/badge/license-GPLv3-blue)
![QGIS](https://img.shields.io/badge/QGIS-3.28%2B-green)

---

## What it does

The method follows Alpha & Winter (1971), Raisz (1931) and Ridd (1963):
contour levels are made invisible, every relief point is displaced north
in proportion to its height, and fall lines with light-dependent density
and hidden-surface removal build the oblique view. The higher the
mountain, the taller its profile.

Two algorithms share one decoration layer:

* **Landform map (Hammond + Mower + Alpha)** — hybrid: Hammond
  classification splits mountains (hachured) from plains (stippled),
  with Mower-style generalization. Works at a capped working resolution.
* **Classic physiographic (full resolution)** — uniform engraved
  hachuring across the whole surface at full DEM resolution, with
  automatic strip tiling for very large sheets.

## Features

- Paper/ink presets: sepia, blueprint, cyanotype, old map, plain white,
  diazotype — all line work follows the preset
- Hypsometric fill (Patterson, Bartholomew, Peucker, Imhof) or thematic
  fill colored from the QGIS layer style, draped over the displaced relief
- Separate overlay layers: rivers, lakes, seas, marshes, roads,
  settlements with haloed labels, and five land cover textures
- Engraved hydrography patterns: coastal vignette, lake hatching, marsh tufts
- Auto-sea from the DEM with island holes preserved
- Large-form shading: two-tone lithographic shadow spot **or**
  XIX-century anaglyptography line engraving
- Sheet decoration: frames (including a checkered map border of degree
  fractions), graticule ticks in D°MM′, old-style scale bar, compass rose
  pointing to true north
- Old-print emulation: halftone dot screen, paper grain, color misregistration
- Canvas rotation 0/90/180/270°, relative scene scaling for gentle terrain
- Vector export to SVG/PDF

## Installation

**From the QGIS Plugin Manager** — search for "Raisz-style Relief".

**Manually** — copy the `raisz_relief` folder into your QGIS plugin
directory and enable it in *Plugins → Manage and Install Plugins*:

| OS | Path |
|---|---|
| Windows | `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\` |
| Linux | `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/` |
| macOS | `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/` |

The algorithms then appear in the Processing Toolbox under
**Raisz-style Relief**.

### Requirements

QGIS 3.28 or newer. All Python dependencies ship with QGIS/OSGeo4W:
numpy, scipy, matplotlib, rasterio, shapely (≥ 2.0), pyproj, affine, GDAL.

---

## Recommendations for use

### Coordinate reference system

**Use a projected, metric CRS** — UTM for a single region, Albers or
Lambert Conformal Conic for a country-sized sheet. The method measures
local relief and slopes in meters, so a geographic CRS (EPSG:4326,
degrees) distorts them badly: one degree of longitude is not one degree
of latitude anywhere except the equator, and the hachures come out
stretched. The landform algorithm warns you when the DEM is in degrees.

Reproject the DEM first (*Raster → Projections → Warp*), don't rely on
on-the-fly reprojection — the plugin reads the file, not the canvas.

Vector overlays may be in any CRS: they are reprojected to the DEM CRS
and clipped to its extent automatically.

### Scene selection

The plugin performs best in regions with mountainous or strongly
dissected terrain expressed at a regional scale. Weakly dissected
lowland areas may produce less convincing results. For a more balanced
composition, select scenes with lowland terrain in the foreground or use
view rotation to bring the plains forward.

### Resolution

**Aim for about 6,000 px on the longer side of the DEM.** This is the
sweet spot where the engraving reads as line work rather than as noise
or as coarse scribble:

- Below ~2,000 px the strokes become sparse and the framework blocky.
- Around 6,000 px, you get a dense, even texture that prints beautifully
  at A2–A1 sizes and still renders in a few minutes. The progress bar may
  appear to freeze at 40–50%; this is normal.
- Above ~12,000 px the gain is marginal, while memory and time grow
  quadratically. Use strip mode (see below) if you go there anyway.

The **landform algorithm** resamples internally to *Working resolution*
(default 2,000 px) — raise it to 3,000–4,000 px for a final sheet. The
**Classic algorithm** always works at full DEM resolution, so prepare
the DEM at the intended output size: resample it beforehand rather than
feeding it a 30,000 px raster. Without strip tiling (see below), very
large scenes may take several hours to render and can exhaust available
RAM.

Match the DEM resolution to the sheet, not to the source data: a
1-arcsecond SRTM tile of a whole country is far more detail than a
printed sheet can hold, and downsampling it first produces a cleaner,
faster, more Raisz-like result.

### Memory and large sheets (classic algorithm)

Leave *Strip height* at 0 and set a realistic *Memory limit* (default
8 GB). If the estimate exceeds the limit, strip tiling switches on
automatically and the sheet is built in horizontal strips at full
resolution without ever holding the whole DEM in memory. In strip mode
the fill, decoration, shading and engraving are computed once on a
downsampled grid, so they cost almost nothing.

Note: canvas rotation is not applied in strip mode yet.

### Gentle terrain

Low hills, plateaus and steep-but-low coastal cliffs render poorly with
absolute settings — the displacement is tiny and the sheet looks empty.
Turn on **Relative scene scale**: the displacement is normalized so the
relief reaches a target share of the sheet height (12 % by default), and
the contour interval is derived from a number of elevation belts instead
of meters. In this mode set *Vertical exaggeration* to about **1.0** —
it acts as a multiplier on the target, and the default 2.2 doubles it.

Add **Relative slopes** if the line work is still sparse: stroke cutoff
and weight come from scene percentiles instead of fixed 4°/45°. The
trade-off is that stroke weight is no longer comparable between sheets.

> **Warning:** Relative Slope and Scale Mode are highly experimental.
> This option is being developed primarily for small, large-scale scenes.
> It may produce highly unpredictable results, often bearing little
> resemblance to the appearance you intended.

### Vertical exaggeration and view

Start at 2.0–2.5 in absolute mode. Higher values look dramatic but
occlude the terrain behind ridges — the hidden-surface removal will
simply delete it. Lower the *View angle* for a flatter, more panoramic
sheet; raise it toward 60–70° for something closer to a plan.

Mountains displaced upward deliberately overlap the top frame — that is
the authentic panoramic-map effect, not a bug.

### Style

- Keep the sheet monochrome (fill = *None — paper only*) for the closest
  match to Raisz's originals; water and roads then differ by pattern, not
  by color, which is the whole point of the manner.
- Turn decoration on gradually — frame, then graticule, then scale bar
  and compass. Everything is off by default so you can judge each addition.
- Hydrography patterns and land cover textures are expensive on huge
  polygon sets; test on a small extent first.
- **Anaglyptography** works best either *instead of* fall lines (disable
  hachures, keep the framework) or *under* them with small spacing and
  low intensity.

### Vector output

Choose `.svg` or `.pdf` in the output file dialog. Line work exports as
true vectors; fills, dot screen and paper grain are embedded as raster
underlays, so files grow. Color misregistration is PNG-only and is
skipped for vector formats.

---

## Documentation

Full parameter reference: [docs/PARAMETERS.md](docs/PARAMETERS.md).
Version history: [CHANGELOG.md](CHANGELOG.md).

## References

- Raisz, E. (1931). The physiographic method of representing scenery on maps. *Geographical Review*, 21(2), 297–304.
- Alpha, T. R., & Winter, W. (1971). *Cartographic technique: block diagrams*. USGS.
- Ridd, M. K. (1963). The proportional relief landform map. *Annals of the AAG*, 53(4), 569–576.
- Hammond, E. H. (1964). Analysis of properties in land form geography. *Annals of the AAG*, 54(1), 11–19.

## License

GNU General Public License v3.0 or later — see [LICENSE.md](LICENSE.md).

Copyright (C) 2026 Maksim Boiko

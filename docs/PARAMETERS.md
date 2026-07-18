# Raisz-style Relief — Parameter Reference

QGIS Processing plugin for presentation-quality physiographic relief maps
in the manner of Erwin Raisz. Two algorithms share one decoration layer:

* **Landform map (Hammond + Mower + Alpha)** — hybrid: hachured mountains,
  stippled plains, works at a capped working resolution.
* **Classic physiographic (full resolution)** — uniform engraved hachuring
  over the whole surface at the full DEM resolution, with optional strip
  tiling for very large sheets.

Output: PNG, SVG or PDF (chosen by the output file extension). All vector
layers are reprojected to the DEM CRS and clipped to its extent
automatically. Dependencies (bundled with QGIS/OSGeo4W): numpy, scipy,
matplotlib, rasterio, shapely, pyproj.

---

## 1. Core relief parameters

| Parameter | Default | Meaning |
|---|---|---|
| Digital elevation model (DEM) | — | Input raster. A metric CRS (e.g. UTM) is recommended for the landform algorithm. |
| Contour interval, m | 40 | Vertical spacing of the invisible contour levels the hachures hang from. Smaller = denser stroke rows. |
| Vertical exaggeration | 2.2 | Scales the northward oblique displacement: the higher the mountain, the taller its profile. |
| View azimuth (canvas rotation) | north up | Rotates the whole canvas 90/180/270° to view the relief from another side. Graticule and compass follow. |
| View angle above horizon, deg | 40 | Lower angle → stronger displacement. |
| Light azimuth / altitude, deg | 315 / 45 | Shared light source: hachure density, hillshade blend and large-form shading all use it. |
| Base fall-line spacing, px | 4 | Horizontal spacing between strokes before light modulation. |
| Min slope for a stroke, deg | 4 | Gentler slopes get no hachures. |
| Draw hachures / contour framework | on | The two line systems of the classic look. |

### Landform algorithm only

| Parameter | Default | Meaning |
|---|---|---|
| Working resolution (max side, px) | 2000 | The DEM is resampled to this cap; higher = finer detail, slower. |
| Hammond classification window, m | 3000 | Moving-window size for the local relief range. |
| Plains threshold mode | midpoint + width | How plains/mountains split: two thresholds, midpoint+width, canonical Hammond classes, or auto percentiles (draft). |
| Plains dot spacing, px | 4 | Stipple density on plains (smaller = denser). |
| Densify valley dots toward mountains | on | Classic manner: stipple thickens near mountain fronts. |
| Outline mountain feet (dotted) | on | Dotted baseline between hachures and stipple. |

### Classic algorithm only

| Parameter | Default | Meaning |
|---|---|---|
| Memory limit, GB | 8 | Estimated memory above the limit auto-enables strip tiling instead of crashing. |
| Strips: strip height, rows | 0 | Manual strip tiling (0 = single pass). View rotation is not applied in strips yet. |

---

## 2. Paper and fill

| Parameter | Default | Meaning |
|---|---|---|
| Paper type (paper/ink preset) | Sepia | Paper+ink color pair: Sepia, Blueprint, Cyanotype, Old map, Plain white, Diazotype. All line work, waters and sheet decoration derive their colors from it. |
| Relief fill | None | One list: **None** (bare paper), **Hypsometric** with a palette (Patterson, Bartholomew, Peucker, Imhof — absolute elevations), or **Thematic** (colors from the QGIS style of the thematic layer). The fill is draped over the displaced relief with hidden-surface removal. |
| Thematic layer | — | Polygons used when fill = Thematic. |
| Fill opacity (0–1) | 0.85 | Advanced. |
| Blend hillshade into hypsometry (0–1) | 0.35 | Advanced; Imhof benefits from ~0.5. |
| Set elevation range manually / min / max | off | Advanced: keeps palette colors comparable across sheets. |
| Stretch palette to data (draft) | off | Advanced: percentile stretch, colors lose absolute meaning. |
| Hand jitter of stroke width (0–1) | 0 | Advanced: random WIDTH variation along fall lines (not positional wobble). |

### Large-form shading (advanced, mutually exclusive styles)

| Parameter | Default | Meaning |
|---|---|---|
| Large-form shading | None | **Shadow spot** — two-tone flat lithographic shadow (half shadow + core, crisp edge) of generalized large landforms; **Anaglyptography** — XIX-century engraving: parallel lines bent by the relief, thicker in shade, vanishing in light. |
| Shading intensity (0–1) | 0.3 | Spot: tone opacity (try 0.4–0.5). Engraving: max line weight (try 0.25–0.35). |
| Shadow spot: generalization window, px | 120 | Larger window → only the biggest ridges cast shadows. |
| Anaglyptography: line spacing, px | 6 | Spacing of the engraved lines. |

---

## 3. Decoration layers (all optional)

Vector layers, grouped together in the dialog: Rivers (lines), Lakes,
Seas, Marshes (polygons); land cover polygons — Forest, Sand/dunes,
Ice/glaciers, Scrub, Grassland/steppe; Roads (lines); Settlements
(points + polygons) with a label field.

On paper presets everything is drawn monochrome in ink (the Raisz way);
over colored fills water turns blue and roads dark red. Rivers pass
under area waters; roads and settlements draw above the hachures;
labels are haloed with the paper color. Land cover textures draw above
the hachures but below area waters, clipped behind mountains.

| Parameter | Default | Meaning |
|---|---|---|
| Auto-sea from DEM | off | Builds a water polygon at the given level directly from the DEM; island holes preserved. |
| Sea level, m | 0 | Threshold of the auto-sea. |
| Hydrography patterns | off | Coastal vignette along true shores, hatching in lakes, tuft symbols in marshes. |

---

## 4. Sheet decoration (advanced, all off by default)

| Parameter | Default | Meaning |
|---|---|---|
| Sheet: frame | None | Single, Double thin, Thick-thin (classic), or **Map border** — a narrow checkered band of black-and-white degree fractions along the outer frame. Relief displaced upward overlaps the top frame (authentic panoramic effect). |
| Sheet: graticule ticks with labels (D°MM′) | off | Any CRS via WGS84; grid step 15′ or coarser (seconds always zero, omitted); at most 3 labels per side, overlap-checked; hemispheres N/S/E/W. |
| Sheet: scale bar (old style) | off | Four black-and-white segments, lower-left; nice-number length via WGS84 haversine — correct along the sheet horizontal. |
| Sheet: compass rose / north arrow | None | Cartouche in the upper-right pointing to TRUE north computed from the CRS — honest on rotated canvases and converging projections. |

---

## 5. Print emulation (advanced, all off by default)

| Parameter | Default | Meaning |
|---|---|---|
| Print: halftone dot screen | off | 45° dot grid between the fill and the line work. |
| Print: paper grain | off | Irregular deterministic noise over the whole sheet (no tiling). |
| Print: color misregistration, px | 0 | R channel shifted right, B left on the finished PNG (old lithography). PNG only; skipped for SVG/PDF. |

---

## 6. Practical notes

* **SVG/PDF**: pick the extension in the output file dialog. Line work
  exports as true vectors; fills, dot screen and grain embed as raster
  underlays (file size grows).
* **Huge DEMs (classic)**: leave strip height at 0 — strips auto-enable
  when the memory estimate exceeds the limit. In strip mode the fill,
  decoration, shading and engraving are computed on a downsampled grid,
  so they are almost free.
* **Anaglyptography** works best either instead of fall lines (disable
  hachures, keep the framework) or under them with small spacing and low
  intensity.
* **Land cover from OSM**: the type is recognized by keywords in the
  attribute value, Russian and English alike (forest/лес, sand/песок…).

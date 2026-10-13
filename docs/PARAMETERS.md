# Raisz-style Relief — Parameter Reference

QGIS plugin for presentation-quality physiographic relief maps in the
manner of Erwin Raisz. Two algorithms share one decoration layer:

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

## 0. Where to find a parameter (since 7.8.0)

Each algorithm has its own window, opened from the toolbar or from
**Raster → Raisz-style Relief**. Parameters are sorted into tabs:

| Tab | Boxes |
|---|---|
| **Main** | Input and output (DEM, contour interval, working size, DPI, output file) · Scene view (angle, azimuth, vertical exaggeration, local base, smoothing) · Relative scene scale · Large sheets *(classic only: strip height, memory limit)* |
| **Strokes and light** | Hachures (on/off, spacing, widths, slope thresholds, hand jitter) · Light and shadow (light direction, cast shadow) · Stroke clean-up (thalwegs, gentle ground, stray strokes) |
| **Plains** *(landform only)* | Hammond classification · Plains stipple · Framework |
| **Fill and paper** | Paper and fill · Manual elevation range · Large-form shading · Watercolour |
| **Layers** | Waters · Land cover · Lines · Settlements |
| **Sheet and print** | Sheet decoration · Old-print emulation |

The fields are the algorithm's own: labels, defaults, ranges and layer
pickers are exactly those of the Processing dialog. Hover a field for
its description; the algorithm help sits on the right of the window.
Values are remembered between sessions; *Restore Defaults* resets them.

A field the current settings do not use is greyed out; its tooltip
names the setting it depends on.

**Relief presets** (row above the tabs, since 7.10.0) fill the stroke
and relief fields — vertical exaggeration, local basis, contour
interval, stroke spacing and weight, slope threshold, stroke clean-up,
cast shadow, relative mode — and nothing else. Every field a preset
does not name returns to the algorithm default. The local basis is given
in metres on the ground and converted with the DEM pixel size (clamped
to 15–1500 px); the contour interval is computed from the DEM for about
5 px between contours. User presets (*Save as…*) store the fields as
they are. *Analyze DEM* reads the DEM and
suggests a contour interval (see section 1).

The window, parameter names, help and log follow the QGIS interface
language; Russian is included. The tables below use the English names.

The **Processing Toolbox** keeps both algorithms with the full flat
parameter list — use it for batch mode, the graphical modeler and
scripts. *Open in Processing…* in the plugin window hands the current
values over to the standard dialog.

The tables below list every parameter regardless of the tab it is in.

---

## 1. Core relief parameters

| Parameter | Default | Meaning |
|---|---|---|
| Digital elevation model (DEM) | — | Input raster. A metric CRS (e.g. UTM) is recommended for the landform algorithm. |
| Contour interval, m | 40 | Vertical spacing of the invisible contour levels the hachures hang from. Smaller = denser stroke rows. *Analyze DEM* suggests a value that puts neighbouring contours about 5 px apart at the median slope of the hachured ground. |
| Vertical exaggeration | 2.2 | Scales the northward oblique displacement: the higher the mountain, the taller its profile. |
| View azimuth (canvas rotation) | north up | Rotates the whole canvas 90/180/270° to view the relief from another side. Graticule and compass follow. |
| View angle above horizon, deg | 40 | Lower angle → stronger displacement. |
| Light azimuth / altitude, deg | 315 / 45 | Shared light source: hachure density, hillshade blend and large-form shading all use it. |
| Base fall-line spacing, px | 4 | Horizontal spacing between strokes before light modulation. |
| Min slope for a stroke, deg | 4 | Gentler slopes get no hachures. |
| Stroke weight from the scene's slopes | off | Advanced. Full stroke weight at the 95th percentile of the land slopes (15–45°) instead of at 45°. Gentle relief gets tone; mountain scenes are unchanged. Ignored in relative mode. |
| Break strokes in thalwegs (0–1) | 0.7 | Stops a stroke where flow lines converge closer than the stroke spacing, so strokes from opposite slopes stop fusing into dark blots along the valley floor. 0 = off. |
| Shorten strokes on gentle ground (0–1) | 0.6 | Scales the descent at which a stroke breaks. Without it a stroke on gentle ground is as long as the bench spacing and reads as a scratch. 0 = off. |
| Thin out stray strokes (0–1) | 0.4 | Removes strokes whose surroundings describe too few contour levels — a stroke on a single contour depicts no form. 0.4 needs 2 levels, 1.0 needs 4. Resolution-independent. 0 = off. |
| Cast shadow from the terrain (0–1) | 0.5 | Darkens ground a neighbouring ridge hides from the sun. Diffuse light cannot express this: a ridge shadow falls on lit slopes too. Azimuth/altitude from the light parameters. 0 = off. |
| Watercolour the fill (0–1) | 0 | Paper grain, a wet edge along colour boundaries, and Kubelka-Munk glazes for land cover and waters. Needs a fill to be enabled; land cover symbols and water patterns are unaffected. |
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
Ice/glaciers, Scrub, Grassland/steppe; Roads (lines); Thematic line layer
(lines); Settlements (points + polygons) with a label field.

On paper presets everything is drawn monochrome in ink (the Raisz way);
over colored fills water turns blue and roads dark red. Rivers pass
under area waters; roads and settlements draw above the hachures;
labels are haloed with the paper color. Land cover textures draw above
the hachures but below area waters, clipped behind mountains.

| Parameter | Default | Meaning |
|---|---|---|
| Auto-sea from DEM | off | Builds a water polygon at the given level directly from the DEM; island holes preserved. |
| Sea level, m | 0 | Threshold of the auto-sea. |
| Areas without data (nodata) shown as | Plain | What to do where the DEM has no data. **Plain** fills with the nearest elevations (previous behaviour), which reads as a flat plain. **Sea** floods the gap at sea level and adds it to the sea polygons. **Paper** leaves it undrawn — no fill, no strokes, no framework. In every mode the nodata border counts as an artificial edge, so no coastal vignette runs along it. |
| Settlement label font | Default | Font family for place names: Default, Serif, Sans-serif, Monospace, Cursive, or Fantasy. Generic matplotlib families are used so they resolve on any system. |
| Settlement label and marker size | 1.0 | Multiplier over the automatic, sheet-relative size. The label scales with the sheet instead of being a fixed point value, so place names no longer shrink on large DEMs; the marker, its offset and halo scale with it. Range 0.2–5.0. |
| Hydrography patterns | off | Coastal vignette along true shores, hatching in lakes, tuft symbols in marshes. Polygon holes are honoured: islands keep their own shore band, and hatching stays off them. |
| Styling from layer styles | off | Colour of area waters and land cover taken from those layers' own QGIS styles instead of the theme (first symbol of the renderer). Patterns and textures are kept; only the colour changes. A layer without a colour keeps the theme default. The thematic line layer always uses its style regardless of this box. |

---

## 4. Sheet decoration (advanced, all off by default)

| Parameter | Default | Meaning |
|---|---|---|
| Sheet: frame | None | Single, Double thin, Thick-thin (classic), or **Map border** — a narrow checkered band of black-and-white degree fractions along the outer frame. Where relief displaced upward juts past the top edge, the top frame line is broken along its silhouette rather than drawn over it. |
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

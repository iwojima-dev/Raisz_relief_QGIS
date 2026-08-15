# Changelog — Raisz-style Relief

All notable changes to this project are documented here.

## 7.7.0 — Grouped parameter dialogs (2026-08-14)

The algorithm dialog is decluttered: 75 of the 85 parameters move into
five windows of their own, opened by "Configure..." buttons.

| Group | Fields |
|---|---|
| Strokes and light | 15 |
| Plains and Hammond classification | 16 |
| Fill, paper and shading | 14 |
| Decoration layers, waters and labels | 21 |
| Sheet decoration and print | 9 |

The main panel keeps the DEM, contour interval, working size, DPI, output
and the scene view settings — angle, azimuth, vertical exaggeration, local
base, smoothing, relative mode, and for the classic algorithm strip tiling
and the memory cap. Those are tuned per DEM rather than chosen once.

Next to each button a summary line shows what differs from the defaults;
the same summary is written into the help panel on the right.

**Existing parameters are unchanged.** Rather than one composite
parameter, a service button parameter per group edits the values of the
ordinary fields. Batch mode, the graphical modeler and calls from scripts
keep seeing ordinary parameters and keep working; the fields are hidden
only in the standard dialog.

Fields absent from a given algorithm are not shown — the classic and
landform algorithms have different parameter sets.

Setting `HIDE_ORIGINALS = False` at the top of `ui_binding.py` restores
the previous look: the buttons stay, the original fields are not hidden.

## 7.6.1 — Watercolour fill (2026-08-12)

Optional watercolour styling of the fill, off by default: one strength
parameter in the advanced block, and it needs a fill to be enabled.

Paper grain, a wet edge along colour boundaries and a slight wobble of
those boundaries are applied to the fill in plan view, before it is
draped over the relief -- so the texture stays with the colour instead of
drifting across the hachuring.

Land cover and waters receive glazes laid by Kubelka-Munk rather than
alpha blending. A thin layer passes light down to the substrate and back,
so forest over ochre and forest over green come out as different hues,
which alpha blending cannot do. Each pigment is defined by how a unit
layer looks on white paper and over black; K and S follow from that pair,
and no spectral measurements are needed. The difference between the two
swatches is what sets the hiding power.

Area waters are watercoloured as a layer of their own, denser at the
shore and lighter towards the middle of large bodies. The shoreline
stroke, the coastal vignette, lake hatching and marsh tufts are unchanged,
and so are the land cover symbols: the wash sits *under* the relief, the
way a glaze sits under a pen drawing.

Method after Bousseau et al. (NPAR 2006) for the stylisation and Curtis
et al. (SIGGRAPH 1997) for the pigment model.

## 7.5.0 — Cast shadow and scene diagnostics (2026-08-08)

Ground hidden from the sun by a neighbouring ridge is now darkened.
Diffuse illumination alone could not express this: a north-facing slope is
always dark, but the shadow of a ridge falls on lit ground as well.
Azimuth and altitude come from the existing light parameters; the strength
is a new parameter, on by default at half strength. Shadow length matches
the analytic `H / tan(alt)` to within 5%.

The log now opens with a scene diagnostic: resolution and extent,
elevation range and percentiles, median and P90 slope, the share of the
area below the stroke threshold, and the contour bench spacing. Hints
follow when a value falls outside a sensible range -- bench spacing too
tight or too wide for the chosen contour interval, a mostly gentle scene,
too small an elevation range.

## 7.4.0 — Stroke engine (2026-08-08)

Three long-standing artefacts of the hachuring, each with its own strength
parameter in the advanced block.

**Blots along valley floors.** A stroke now stops where flow lines
converge closer than the stroke spacing. The measure is the divergence of
the unit fall vector -- the very direction the tracing follows -- which is
a direct measure of two neighbouring strokes about to merge, not an
indirect valley indicator. In the same zone the shade-driven
densification, extra width and higher opacity are damped: a thalweg is
shaded and concave at once, so all three used to pile up in one place.

**Long strokes on gentle ground.** The coefficient now scales the descent
at which a stroke breaks, which is what actually sets stroke length, so
the effect holds across the whole slope range. On gentle ground a stroke
becomes a short mark instead of a scratch across empty paper.

**Stray strokes.** Thinning is by how many distinct contour levels the
hachuring around a stroke describes. A stroke on a single contour depicts
no form; sparse but honest hachuring on a gentle swell still crosses
several levels. The measure does not depend on DEM resolution, so one
setting works for 30 m, 90 m and coarser open elevation data.

All three work in every rendering path. In strip tiling the thinning runs
once over all strips, so strokes at a seam are not cut for want of
neighbours in the adjacent strip.

## 7.3.1 — Thematic lines and styling from layer styles (2026-07-25)

Two additions around taking colour from the QGIS layer style.

**Thematic line layer.** A new line input, drawn above the hachuring in
the colour, width and dash pattern of the layer style -- per feature and
under any renderer -- and clipped where the terrain hides it, the same
treatment roads already get. The style is always used for this layer,
regardless of the checkbox below.

**Styling from layer styles.** A single checkbox, off by default, so
colours keep coming from the paper/fill theme as before. With it on, the
colour of area waters (seas, lakes, marshes) and of land cover (forest,
sand, ice, scrub, grassland) is taken from those layers' own styles;
categorized and graduated renderers are reduced to their first symbol.

The principle is that the tool stays neutral and does not police taste --
pink rivers on a blueprint preset are a deliberate choice by whoever ticks
the box -- while the default protects anyone who leaves it alone. Our own
graphics are kept in every case: the coastal vignette, lake hatching,
marsh tufts and land cover textures stay, they are simply recoloured.
Where a layer is missing or carries no colour, the theme colour remains.

## 7.3.0 — Relative mode reworked (2026-07-25)

Relative mode is meant for gentle scenes -- low hills, plateaus, low but
steep coastal cliffs -- where absolute displacement leaves the drawing
almost flat. The previous version stretched the finished drawing, which
looked poor.

Now the relief is amplified *before* the hachures are drawn, so slopes,
contour density and stroke weight respond to it and the scene is drawn
like a mountain rather than a stretched plain. The amplification is
selective: small steep forms (scarps, coastal cliffs) are raised, while
plains, broad gentle hills and DEM noise stay low. Contour spacing now
follows the local relief instead of the full elevation range.

The separate "relative slopes" option is gone -- slope handling is folded
into relative mode. Relative mode now works in every path, including strip
tiling of large sheets. The hypsometric fill keeps the true elevation
colours.

Also: the Diazotype paper/ink preset was corrected to match a real
diazo-print scan (warm ochre paper, dark plum line).

## 7.2.9 — Waters clipped behind mountains (2026-07-24)

Area waters (lakes, seas, marshes, settlement polygons) are now correctly
hidden where the oblique view puts them behind a ridge. Previously a
partially occluded polygon was drawn whole, so a bay behind the middle of
a ridge spilled out in front of the mountain. It now gets a real gap, and
a water edge peeking from behind a crest shows only its visible part.
Coastal vignettes, lake hatching and marsh tufts follow the visible part
too.

## 7.2.8 — Decoration behind mountains (2026-07-24)

Rivers, roads, settlements and area waters were drawn on top of the
relief even where the oblique view should hide them behind a ridge.

The hidden-line machinery (the `vis` floating-horizon mask) has existed
since July and works in the ordinary path: `classic_core` and
`physio_core` pass `vis` into `draw_infrastructure`. But there were two
independent gaps.

### Gap 1 — strip mode did no clipping at all

`classic_striped` had **`vis=None`** in three consecutive calls: land
cover, area waters, infrastructure. Every large scene goes through strip
mode, which is exactly where the defect shows.

Not an oversight: in strip mode a full-sheet mask does not exist — it is
computed per strip and discarded, otherwise the whole point of the mode
is lost. The decoration, meanwhile, is drawn at the end over the
downsampled `disp_ds`. And while `to_screen` rescales coordinates into
the downsampled grid via `_DISP_SCALE`, `_vis_at` did not — it indexed
the mask directly. A downsampled mask could not be passed at all, so the
stub remained.

Fixed:

- `compose._vis_at` now honours `_DISP_SCALE`, rescaling full-sheet
  coordinates into the mask grid exactly as `to_screen` does. In the
  ordinary path (`_DISP_SCALE is None`) behaviour is unchanged.
- `classic_striped` builds a downsampled visibility mask from `disp_ds`
  with the same floating-horizon formula used for the strips, and passes
  it to all three calls. In nodata mode "paper" the mask is additionally
  gated by `valid_ds`.

### Gap 2 — area waters were never clipped, in any mode

`draw_area_waters` had no `vis` parameter at all, so lakes, seas,
marshes, settlement polygons and the hydrography patterns (vignette,
hatching, tufts) were always drawn over the mountains, in the ordinary
path too.

Fixed: the function takes `vis`. Pattern lines are cut per segment via
`draw_map_segments(vis=…)`, like every other line.

For polygons a `_poly_hidden` test was added: the object is skipped when
**none** of its nodes is visible, i.e. it sits wholly behind a ridge.
Partially occluded ones are kept whole — there is no way to clip a
vector fill by an arbitrary raster mask, and cutting one in half is
worse than leaving it (a lake in a valley is almost always visible along
at least one edge).

### Verification

Synthetic scene: a ridge across the sheet, 40 px displacement. A point
behind the ridge is hidden, one in front is visible — both in the
ordinary path and in strip mode with a half-resolution mask, confirming
the coordinate rescaling is correct. A polygon wholly behind the ridge
is dropped; one in front is kept.

## 7.2.7 — Vector export and a PROJ crash (2026-07-24)

### The process crashed while drawing sheet decoration

Symptom: QGIS went down entirely with `Windows fatal exception: access
violation` in `sheet._lonlat_fn` → `pyproj.CRS.from_user_input` → PROJ
`DatabaseContext::toWGS84AutocorrectWrongValues`. Not a Python exception
— a native crash that `try/except` cannot catch.

Cause: PROJ contexts are not thread-safe (one context, one thread). A
Processing algorithm runs in a worker thread
(`QgsProcessingAlgRunnerTask::run`), while QGIS on the main thread also
uses PROJ — canvas redraws, dialogs, CRS lookups. pyproj and QGIS share
the same loaded PROJ library and its database cache, so creating a CRS
from the worker thread can land in memory another thread is using.

Why it showed up so rarely: `_lonlat_fn` is called only for the map
border (frame=4), graticule ticks or the scale bar — with plain frames
pyproj is never even imported. It also needs the main thread to touch
PROJ at that exact moment, so the same sheet could render fine once and
crash QGIS on the next run.

Fixed: inside QGIS the sheet decoration now uses its own transformer —
`QgsCoordinateReferenceSystem` + `QgsCoordinateTransform` with a local
`QgsCoordinateTransformContext`, without reaching for `QgsProject` from
a foreign thread. pyproj remains a fallback for use outside QGIS
(`except ImportError`). Both call sites were converted: the degree
border with ticks, and the true-north vector for the compass.

Checked against the previous result: `_lonlat_fn` over 500 points
differs by exactly zero, the north vector matches to six decimals, and
4000 points take 9 ms.

### PDF twice as slow as PNG on identical geometry

Measured on a 4965×1836 scene: PNG 385 s, PDF 925 s, identical
parameters. The log showed 2,598,440 stroke segments.

Cause: `displace_clip` emitted **a separate two-point segment for every
edge** of a fall line. A stroke is traced through 10–40 points, so
instead of one polyline it produced that many independent paths. Agg
copes — rasterization cost scales with area, not object count — but
vector backends pay a **fixed cost per path**, hence the extra 540 s ≈
0.2 ms × 2.6M.

Fixed: contiguous visible points are merged into a single polyline. The
geometry is unchanged — a check over 2000 random visibility patterns
found **0 discrepancies** between the edges of the new polylines and the
old pairs. As a side effect the line work is cleaner: a continuous path
joins properly instead of showing butt caps at every bend.

One subtlety about the pen: with `hand_jitter > 0` the width varies
**along** the stroke, while a path has a single width. So merging is
enabled only without jitter; with jitter the polylines still fall back
to edges and the pen-pressure simulation is fully preserved.

### Also

- A progress tick with the path count was added before `savefig`:
  writing a PDF no longer looks like a freeze on the decoration step
  (there was no message between the two, so a multi-minute write showed
  as "96% Decoration").
- **Note:** the `fall_segs` statistic now counts paths, not edges. The
  log will show a number 10–15× smaller than 2,598,440 — no strokes were
  lost, the unit changed.

## 7.2.6 — Qt6 compatibility; settlement label font and size (2026-07-20)

### Qt6 / PyQt6 compatibility

QGIS 3.40+ may be built on Qt6, where PyQt6 requires fully qualified
(scoped) enums. The code had 25 old-form references
(`QgsProcessingParameterNumber.Double`, `…Definition.FlagAdvanced`,
`QgsProcessing.TypeVectorPolygon`, etc.) across four files — on Qt6 they
raised `AttributeError` right in `initAlgorithm`.

- The minimum QGIS version is raised from 3.28 to **3.40**, where the
  scoped forms exist natively, so no Qt5 `try/except` fallback is needed;
  `supportsQt6=True` is declared in `metadata.txt`.
- `_base.py` defines one set of aliases (`NUM_DOUBLE`, `NUM_INT`,
  `FLAG_ADVANCED`, `SRC_POLYGON/LINE/POINT`); the algorithms import
  `NUM_DOUBLE as D, NUM_INT as I`, keeping the scoped form in one place.
- The three `TypeVector*` values do not merely gain a prefix in Qt6 —
  they move from `QgsProcessing` to `Qgis.ProcessingSourceType`; handled,
  and the now-unused `QgsProcessing` import removed.

### Settlement label font and size

The label font size was a constant in `theme.py` (`label_size=9`) —
absolute points — while all sheet decoration is sized as a fraction of
the margin via `sheet._pt()`. Points-per-data-pixel do not depend on
scene size (~0.74), so coordinate labels grow with the canvas but place
names do not: on a scene twice as wide the lag is already threefold.

Two new parameters in the shared decoration group (both algorithms):

- **Settlement label font** — an enum of generic matplotlib families
  (default, serif, sans-serif, monospace, cursive, fantasy), chosen over
  named typefaces so they resolve on any system.
- **Settlement label and marker size** — a multiplier, 1.0 = auto by
  sheet, range 0.2–5.0. A multiplier rather than points, so the value
  need not be re-tuned when the scene changes.

`sheet.settle_style()` computes the sizes from the margin (base
`0.11·margin`, 7 pt floor); the marker area scales as the square of the
coefficient, so the marker/label ratio is preserved. At 1.0 the fjord
scene renders 8.81 pt vs the former 9 — visually unchanged by default,
but now it scales.

Also fixed along the way: the settlement marker edge was hard-coded white
(`edgecolors="white"`), while the label halo always came from the theme;
on sepia, blueprint and similar presets the white edge stood out. It now
uses the same halo as the label. The label offset (fixed 3 px) and the
halo/edge widths now scale with the font size too.

## 7.2.5 — Technical re-release for the QGIS Plugin Repository (2026-07-20)

A narrow fix for re-submission to the QGIS Plugin Repository, published
separately. Proper exception logging was added instead of silently
swallowing errors (`except: pass`), clearing the static-analysis warnings
from the plugin security scanner (Bandit B110). No functional changes;
everything from 7.2.4 onward is in 7.2.6.

## 7.2.4 — Decoration micro-fixes (2026-07-19)

**Compass rose and scale bar halved.** Compass: main ray
`1.5*margin → 0.75*margin`, outline width and the "N" glyph size halved.
Scale bar: length `0.22 → 0.11` of the sheet width (the "nice" round
length is still picked the same way), bar height and labels halved.
Cartouche positions in the corners are unchanged.

**Coordinate labels unglued from the trim.** The sheet is saved with
`bbox_inches="tight"`, and `pad_inches` was `0.0`, so the crop ran
flush along the outermost label — the left coordinates sat on the trim
with their top edge. `pad_inches=0.12` (≈3 mm) is now used in all three
cores: the margins widen slightly and evenly on every side, which also
stops the bottom labels, the compass and the scale bar from sticking to
the edge. Tick length and font size were left alone so the frame
proportions do not shift.

**The nodata border counts as a frame; no vignette along it.**
`coastal_vignette` gained an `edges` argument — extra artificial edges.
The cores put `nodata_edges` (rings of the area without data) into the
overlays whenever the DEM has gaps, regardless of the selected mode. The
exclusion zone is the buffer of the union of the sheet frame and those
rings.

This matters most in nodata = *Sea* mode: the gap becomes water, and
without the fix a full coastal band traced its diagonal survey cut — a
pure artifact. Measured on the fjord scene: 146 vignette lines → 142,
removing exactly those that ran along the cut; the real shore is
untouched (identical to *Paper* mode). Runtime is unchanged, 12.4 s
against 12.3 s.

## 7.2.3 — The coastal vignette stopped being the bottleneck (2026-07-19)

Regression in 7.2.2: render time grew from 12 to 25+ minutes (the scene
would never have finished). The coastal vignette was to blame.

**Cause.** In `coastal_vignette` the "keep only the band along the real
shore" selection went through `ering.intersection(coast.buffer(...))`,
and `coast.buffer()` sat INSIDE the loop over rings. While there were no
holes, each polygon had a single ring. After 7.2.2 the sea polygon had
347 of them, and the same buffer was computed 347 times for each of the
3 levels. Measured: **one** such buffer on a 344-ring outline takes
**14.9 s**, with 1032 calls. That is hours, not minutes.

**Fixed in two steps.**

1. The buffer was hoisted out of the loop — it depends only on the level
   k, not on the ring.
2. The technique itself was replaced by an equivalent cheap one. The
   band is the outline pushed inward by `step*k`. A section produced by
   the artificial edge of the territory lies `step*k` from the FRAME; a
   section from a real shore lies `step*k` from the shore. The two sets
   complement each other, so instead of "intersect with a buffer of the
   shore" (geometry of hundreds of rings, expensive) it now "subtracts a
   buffer of the frame" (a rectangle, computed once per call). The
   result is the same: without holes there were 95 band lines, now
   94 — a single degenerate one differs.
3. New `min_island` argument (default 2.0): islands smaller than
   `(2*step)^2` take no part in the band. A full three-line halo around
   a two-pixel skerry is graphic noise, and every ring makes all buffers
   heavier. Neither the fill nor the islands themselves are affected.

**Measured on the fjord scene** (94 polygons, 346 holes, 402 m step):

| | 7.2.1 | 7.2.2 | 7.2.3 |
|---|---|---|---|
| band without holes | 42.2 s | 42.2 s | **9.0 s** |
| band with holes | — | ~4 h | **13.1 s** |
| band lines | 95 | 143 | 143 |

Net result: with islands it is now three times faster than it was
without them before 7.2.2.

## 7.2.2 — Islands in polygons, and nodata modes (2026-07-18)

Symptom: a sea polygon supplied as a layer looked shifted east relative
to the relief, while auto-sea landed exactly. The investigation found
two independent causes; coordinates and projections were innocent —
measuring in pixel space gave a shift of exactly 0 on both axes.

### Cause 1 — polygon holes were dropped

`overlays.extract_polys` returned only the exterior ring (`poly[0]`), so
every interior ring was discarded. On the fjord test scene (94 polygons,
**346 hole rings**) the sea flooded the skerries: 116,688 pixels of land
went under water, 5.7% of the frame. A flooded archipelago on the left,
a correct outline on the right — hence the impression that the body of
water had moved east.

Auto-sea was right because `grid.sea_polygons` builds rings together
with holes and draws them through `compose.draw_poly_holes`.

Fixed: holes are preserved and honored all the way through.

- `overlays.extract_polys` returns `[[outer, hole1, …], …]`;
  `extract_landcover` likewise.
- `grid.as_rings` — one normalisation for an overlay item; it also
  accepts the old "flat" format, so backward compatibility is kept.
- `compose.draw_polys` became a wrapper over `draw_poly_holes`: polygons
  are drawn as a compound path and holes are cut out.
- `patterns._poly` builds `Polygon(shell, holes)` — which taught **all**
  patterns about holes at once: lake hatching and marsh tufts stay off
  the islands, and so do forest and sand stipple, scrub chevrons, grass
  tufts and ice form lines.
- `patterns.coastal_vignette` also bands the island shores (interior
  rings after the negative buffer), as on hand-drawn maps. Auto-sea
  gained this too, having previously lost islands in the pattern.

Verified on real data: agreement with the DEM water mask rose from
IoU 0.844 to **1.000**, with 0 pixels of flooded land.

### Cause 2 — areas without data were rendered as a plain

`grid.read_dem` silently plugged nodata with the nearest valid value. On
a diagonally clipped DEM the western wedge (4.18% of the frame) was
filled with zeros from the edge and produced a perfectly flat surface:
zero relief above the basis, therefore no strokes and no framework — a
**phantom plain** that the sea polygon honestly did not enter. The
second contribution to the "shift".

New parameter **"Areas without data (nodata) shown as"** (both
algorithms, default *Plain* — the previous behaviour):

- **Plain** — filled with the nearest elevations, as before;
- **Sea** — flooded at sea level; the area joins the sea polygons
  (`grid.nodata_polygons`) and is painted with the water style;
- **Paper** — not drawn at all: no fill, no strokes, no framework, no
  plains stipple. A clean sheet, as on maps where the survey did not
  cover a corner.

Implementation:

- `grid.valid_mask` — a data mask robust to average resampling: besides
  the exact nodata comparison it rejects out-of-range values (blending
  −3.4e38 with valid cells yields absurd numbers that the old `z != nd`
  test let through).
- `grid.read_dem` and `read_dem_window` return the validity mask and
  take `nodata_mode`; the computation still runs on the filled DEM,
  otherwise gradients and morphology would fall apart at the edge.
- *Paper* mode is gated through the existing visibility mask
  (`vis &= valid`), so strokes, framework and decoration are cut by the
  same mechanism as lines behind mountains; the fill gets zero alpha
  (`fills.build_base_fill(valid=…)`); the landform core additionally
  gates the `w_plain` and `w_relief` weights so the plains stipple does
  not leak.
- The share of the area without data and the chosen mode are written to
  the Processing log.

## 7.2.1 — Frame no longer sits on top of the mountains (2026-07-18)

**Problem.** With oblique displacement the relief juts past the top edge
of the sheet, yet the top frame line was drawn straight across it. The
frame sits at z=3.5 — above the draped fill (z≈1) but below the strokes
(5) and the framework (4), so hachures drew over the frame while the
relief *body* stayed underneath and the line cut through the silhouette
between strokes.

**Fixed.** Top horizontal frame lines are now broken along the relief
silhouette. The cores pass a new `top_profile` argument to `draw_sheet`
— the per-column minimum screen Y, i.e. `min(row − disp)` over rows.

- `sheet.py`: `_top_gaps` / `_hline_segs` / `_covered_at` split a
  horizontal line into visible runs; with `top_profile` given, `_rect`
  draws the frame as four lines (top one segmented) instead of a
  Rectangle; `_checker_frame` skips top-side checkers hidden by the
  relief (tested at the checker midpoint on the band's inner edge);
  `_draw_ticks` skips a tick and its label when the relief covers its
  base.
- Tolerance `_TOL = 0.75` px: relief flush with a line keeps the line —
  otherwise zero displacement in valleys at the top edge would erase it.
- Side and bottom edges are unchanged; with `top_profile=None` the old
  Rectangle path is used, so backward compatibility is preserved.
- `classic_core.py`, `physio_core.py`: profile computed from `disp`.
- `classic_striped.py`: profile taken from `carried` — after the topmost
  strip it already is the per-column minimum screen Y across the whole
  sheet, so no extra computation is needed.

## 7.2.0 — Relative scene scale (2026-07-18)

**Problem.** Heights were handled in absolute units (meters, degrees), so
a decent render only came out on "mountainous" scenes. Low hills, or
steep but low cliffs (a coastline with ~200 m of relief), produced weak
oblique displacement, a sparse framework and half-empty hachuring.

### Added

**"Relative scene scale" checkbox** (both algorithms, off by default;
default behavior unchanged). When enabled:

- The oblique displacement is normalized to the scene: the p99 of the
  displacement is stretched to a target percentage of the sheet height
  (parameter *target relief height, % of sheet height*, default 12 %).
  p99 rather than max keeps single spikes (masts, DEM artifacts) from
  dominating the normalization.
- *Vertical exaggeration* becomes a multiplier on top of the target:
  1.0 = exactly the target, 2.0 = twice as tall. The default of 2.2 is
  inherited from absolute mode — set it to about 1.0 in relative mode.
- The contour interval is set by a number of elevation belts (parameter
  *number of elevation belts*, default 12): interval = (zmax − zmin) / N.
  This affects both the framework and the fall-line length (a stroke ends
  after descending one interval).

**Separate "Relative slopes" flag** (off by default): percentile
normalization of scene slopes instead of absolute degrees.

- Classic: the stroke cutoff threshold becomes the p30 of non-zero scene
  slopes (instead of 4°), and the full graphic width range becomes p95
  (instead of 45°).
- Landform: slope_ratio is normalized by the p95 of the tangent inside
  the relief zone (w_relief ≥ 0.4). Hammond classification is NOT
  affected — it is computed from local relief upstream.
- Trade-off: cross-sheet comparability of stroke weight is lost — equally
  heavy strokes on different sheets no longer mean equal real steepness.
  A deliberate choice for presentation graphics; if you need a common
  scale, use one large DEM.

### Implementation

- Shared logic in `grid.py`: `rel_scale_k()`, `rel_interval()`,
  `rel_slope_norm()` — one copy for all three cores.
- `classic_core.py`: disp/interval normalization after morphometry;
  slopes go through the scalars slope_norm_deg / min_slope_eff.
- `classic_striped.py`: the coefficients are computed ONCE on the
  downsampled pass and passed into the strips (`_morphometry(disp_scale=,
  slope_norm_deg=)`) — otherwise strips would normalize differently and
  split at the seams. k is dimensionless and identical for the
  downsampled and the full grid (target/ny and p99(disp) scale with the
  pixel the same way). Caveat: p99 and the slope percentiles are computed
  on the downsampled grid, where slopes are systematically gentler than
  at full size, so strokes in strip mode come out slightly heavier than
  in a single pass over the same scene.
- `physio_core.py`: the FINAL disp is normalized (after multiplication by
  w_relief); there is no feedback into classification. The Hammond auto
  thresholds are percentile-based anyway (p40/p85 of LR with absolute
  clamps of 12–50 / 40–150 m); if the whole local relief of a scene is
  below 12 m, the scene honestly becomes plains (stipple only), which is
  correct.
- Diagnostics: every coefficient (p99, k, effective interval, slope
  thresholds) is written to the Processing log.

### Files

grid.py, classic_core.py, classic_striped.py, physio_core.py,
classic_algorithm.py, physiographic_algorithm.py, metadata.txt.

---

## 7.1.0 — Sheet decoration and print emulation

- Sheet decoration: frames (single, double, thick-thin, and a checkered
  map border of degree fractions), graticule ticks with D°MM′ labels
  (any CRS via WGS84), old-style scale bar, compass rose / north arrow
  honoring true north on any projection and on a rotated canvas.
- Old-print emulation: halftone dot screen, paper grain, R/B color
  misregistration (PNG only).
- Large-form shading: a two-tone lithographic shadow spot or XIX-century
  anaglyptography engraving (mutually exclusive).
- UI reorganization: paper/fill/thematic reduced to three fields, all
  vector layers grouped into one block.
- English release with per-parameter tooltips.

## 7.0.0 — Vector export and strip tiling

- Vector export (SVG/PDF): choose the output format for a clean print
  sheet or for editing in vector software (raster fill embedded).
- Strip tiling of the classic mode for huge sheets without memory
  overflow, including decoration.
- Canvas rotation (0/90/180/270°), paper/ink presets (sepia, blueprint,
  cyanotype, old map, white, diazotype), optional stroke width jitter,
  auto-sea from the DEM with island holes preserved, hydrography patterns
  and land cover textures, Hammond A–D landform modes.

## 4.0.0 — Full rework

- Two algorithms (landform + classic hachures) on a shared core.
- Hypsometric fill from elevation (Patterson, Bartholomew, Peucker,
  Imhof) with manual min/max override and optional percentile stretch.
- Thematic fill takes colors from the QGIS layer style (no rendering).
- Fill draped over the displaced relief.
- Automatic background theme: monochrome water on sepia, blue on fills.
- Separate water layers (rivers, lakes, seas, marshes), roads,
  settlements; layers clipped to the DEM extent.
- Memory control in classic mode. PNG output.

## 3.1.0

- Hybrid hachures (classic + Mower), landform classification, fills,
  decoration layers.

# Changelog — Raisz-style Relief

All notable changes to this project are documented here.

## 7.2.5 — Bumped plugin version for re-submission to the QGIS Plugin Repository. (2026-07-20)

### Fixed
- Added proper exception logging instead of silently ignoring errors,
  resolving static-analysis warnings from the QGIS plugin security scanner.

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

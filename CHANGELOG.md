# Changelog — Raisz-style Relief

All notable changes to this project are documented here.

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

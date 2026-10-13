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
"""DEM analysis before a run: scene statistics and a suggested interval.

The render logs a scene diagnostic, but only after the work is done. This
module computes the same quantities up front from a quick read of the DEM,
so the contour interval can be set before the first render rather than
after a wasted one.

The key quantity is the contour BENCH SPACING in pixels -- the map distance
between neighbouring contours at the typical slope. It decides how the
hachuring reads: below ~3 px the contours merge, above ~20 px the strokes
turn long and sparse. The interval is chosen for about 5 px at the median
slope of the HACHURED ground -- steeper than the stroke threshold, where
the strokes are actually drawn. 5 px is not the middle of 3..20 but what
test renders showed (7.10.0): the Himalaya near Pokhara, the massifs of
Rio, the Cape ranges and Hawaii all read best at 4-6 px; at 8 px the
Cape ranges fell apart into separate rows.

A median over the whole frame would fail twice over: half a sea gives a
median of zero, and a lowland between steep massifs (Rio) gives one that
suits neither.

Pure numpy/scipy except read_dem(), which uses GDAL.
"""

import math

import numpy as np
from scipy import ndimage

from ..i18n import tr

TARGET_BENCH_PX = 5.0       # from test renders (7.10.0): Himalaya, Rio,
                            # Cape ranges and Hawaii read best at 4-6 px
SLOPING_DEG = 0.5           # ground gentler than this does not set the median
SMALL_RANGE_M = 300.0       # land relief below this suits the relative mode
MOSTLY_FLAT = 0.65          # share of the LAND below the stroke threshold


def read_dem(path, max_side):
    """Read the DEM averaged down to at most max_side pixels on the longer
    side. Returns dict: z, valid, mpp_read, mpp_native, size_native,
    geographic. GDAL is imported here so the rest of the module stays
    testable outside QGIS."""
    from osgeo import gdal, osr

    ds = gdal.Open(str(path))
    if ds is None:
        raise RuntimeError(tr("Cannot open the DEM: %s") % path)
    W, H = ds.RasterXSize, ds.RasterYSize
    gt = ds.GetGeoTransform()
    k = max(1.0, max(W, H) / float(max_side))
    bw, bh = max(2, int(round(W / k))), max(2, int(round(H / k)))
    band = ds.GetRasterBand(1)
    z = band.ReadAsArray(0, 0, W, H, buf_xsize=bw, buf_ysize=bh,
                         resample_alg=gdal.GRIORA_Average).astype("float64")
    nd = band.GetNoDataValue()
    valid = np.isfinite(z) & (np.abs(z) < 1e30)
    if nd is not None:
        valid &= z != nd
    px = math.hypot(gt[1], gt[4])
    py = math.hypot(gt[2], gt[5])
    mpp = (px + py) / 2.0
    geographic = False
    srs = osr.SpatialReference()
    if ds.GetProjection() and srs.ImportFromWkt(ds.GetProjection()) == 0:
        geographic = bool(srs.IsGeographic())
    if geographic:
        lat = gt[3] + gt[5] * H / 2.0
        mpp *= 111320.0 * max(math.cos(math.radians(lat)), 0.05)
    ds = None
    return dict(z=z, valid=valid, mpp_read=mpp * W / float(bw),
                mpp_native=mpp, size_native=(W, H), geographic=geographic)


def scene_stats(z, valid, mpp, smooth_px=1.0, min_slope_deg=4.0):
    """Elevation and slope statistics of a DEM array (metres per pixel mpp).
    Nodata is filled with the nearest valid value before differentiating,
    so the edge of a gap does not read as a cliff."""
    z = np.asarray(z, dtype="float64")
    valid = np.asarray(valid, dtype=bool)
    if not valid.any():
        raise ValueError(tr("The DEM has no valid cells."))
    if not valid.all():
        idx = ndimage.distance_transform_edt(
            ~valid, return_distances=False, return_indices=True)
        z = z[tuple(idx)]
    if smooth_px and smooth_px > 0:
        z = ndimage.gaussian_filter(z, sigma=float(smooth_px))
    gy, gx = np.gradient(z, float(mpp))
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))[valid]
    zz = z[valid]
    land = slope > SLOPING_DEG
    sloping = slope[land]
    hachured = slope[slope >= max(float(min_slope_deg), SLOPING_DEG)]
    zl = zz[land] if land.any() else zz
    return dict(
        zmin=float(zz.min()), zmax=float(zz.max()),
        z5=float(np.percentile(zz, 5)), z95=float(np.percentile(zz, 95)),
        # the bench spacing matters where strokes are drawn: on ground
        # steeper than the stroke threshold (Rio: lowland at 2 deg, massifs
        # at 20 deg -- the median over all land suited neither)
        slope_med=float(np.median(hachured)) if hachured.size else (
            float(np.median(sloping)) if sloping.size else 0.0),
        hachured_share=float(hachured.size) / max(slope.size, 1),
        min_slope=float(min_slope_deg),
        slope_p90=float(np.percentile(slope, 90)),
        sloping_share=float(sloping.size) / max(slope.size, 1),
        flat_share=float((slope < min_slope_deg).mean()),
        # water and perfect plains excluded: a sea filling half the frame
        # must not make a volcano "gentle" (7.10.0)
        flat_land_share=(float((sloping < min_slope_deg).mean())
                         if sloping.size else 1.0),
        land_range=float(np.percentile(zl, 95) - np.percentile(zl, 5)),
        nodata_share=1.0 - float(valid.mean()),
    )


def bench_px(interval, slope_deg, mpp):
    """Contour bench spacing in pixels at a given slope."""
    t = math.tan(math.radians(max(float(slope_deg), 0.05)))
    return float(interval) / max(t * float(mpp), 1e-9)


def nice_interval(x):
    """Round to the usual contour intervals: 1, 2, 2.5, 4, 5 x 10^k."""
    if not x or x <= 0 or not math.isfinite(x):
        return None
    e = math.floor(math.log10(x))
    cands = [m * 10 ** k for k in (e - 1, e, e + 1) for m in (1, 2, 2.5, 4, 5)]
    best = min(cands, key=lambda c: abs(math.log(c / x)))
    return int(best) if float(best).is_integer() else best


def recommend(stats, mpp_target, interval_now, rel_scale_now=False,
              target_bench=TARGET_BENCH_PX):
    """Turn scene statistics into a suggested interval and plain hints.

    mpp_target -- metres per pixel of the grid the algorithm will actually
    draw on (the working resolution for the landform map, the full DEM for
    the classic one). Returns dict: interval (or None), bench_now,
    bench_rec, hints (list of str)."""
    s = stats["slope_med"]
    hints = []
    rec = None
    bench_now = bench_rec = None
    if s > 0:
        rec = nice_interval(target_bench * math.tan(math.radians(s))
                            * float(mpp_target))
        bench_now = bench_px(interval_now, s, mpp_target)
        bench_rec = bench_px(rec, s, mpp_target) if rec else None
    else:
        hints.append(tr("No sloping ground found -- the scene is flat at "
                        "this resolution; there is nothing to hachure."))
    rng = stats["land_range"]
    flat = stats["flat_land_share"]
    low = rng < 150.0 or (flat > MOSTLY_FLAT and rng < SMALL_RANGE_M)
    if low or flat > MOSTLY_FLAT:
        if low:
            hints.append(tr("The land is low (%.0f m between P5 and P95, "
                            "%.0f%% of it below the stroke slope threshold): "
                            "consider the relative scene scale with vertical "
                            "exaggeration near 1.0.")
                         % (rng, 100.0 * flat))
        else:
            hints.append(tr("The land is gentle but high (%.0f m between P5 "
                            "and P95, %.0f%% of it below the stroke slope "
                            "threshold): lower the slope threshold and "
                            "switch on the stroke weight from the scene's "
                            "slopes. The relative scene scale would inflate "
                            "relief this large.")
                         % (rng, 100.0 * flat))
    if rel_scale_now:
        hints.append(tr("Relative scene scale is on: the contour interval is "
                        "derived from the number of elevation belts, so the "
                        "suggestion applies only if you switch it off."))
    if bench_now is not None:
        if bench_now < 3.0:
            hints.append(tr("At the current interval the contours would sit "
                            "%.1f px apart and merge.") % bench_now)
        elif bench_now > 20.0:
            hints.append(tr("At the current interval the contours would sit "
                            "%.0f px apart: long, sparse strokes.")
                         % bench_now)
    return dict(interval=rec, bench_now=bench_now, bench_rec=bench_rec,
                hints=hints)


def report_lines(stats, rec, mpp_target, interval_now, geographic=False,
                 approximate=False):
    """Human-readable lines for the log pane."""
    out = [tr("elevations %.0f..%.0f m (P5/P95 %.0f/%.0f)")
           % (stats["zmin"], stats["zmax"], stats["z5"], stats["z95"]),
           tr("land %.0f%% of the area; hachured ground (steeper than "
              "%.0f deg) %.0f%%, median slope there %.1f deg, P90 %.1f deg")
           % (100.0 * stats["sloping_share"], stats["min_slope"],
              100.0 * stats["hachured_share"], stats["slope_med"],
              stats["slope_p90"]),
           tr("drawing grid %.1f m/pixel") % mpp_target]
    if stats["nodata_share"] > 0.001:
        out.append(tr("no data: %.1f%% of the frame")
                   % (100.0 * stats["nodata_share"]))
    if rec["bench_now"] is not None:
        out.append(tr("current interval %g m -> contours %.1f px apart")
                   % (interval_now, rec["bench_now"]))
    if rec["interval"] is not None:
        out.append(tr("suggested interval %g m -> contours %.1f px apart "
                      "(aim: about %g px)")
                   % (rec["interval"], rec["bench_rec"], TARGET_BENCH_PX))
    if geographic:
        out.append(tr("WARNING: the DEM is in degrees; metres were "
                      "estimated at the centre latitude. Reproject to a "
                      "metric CRS for a correct result."))
    if approximate:
        out.append(tr("(read at reduced resolution for speed: slopes are "
                      "slightly underestimated, so the suggestion errs "
                      "dense)"))
    return [tr("DEM analysis:")] + ["  " + x for x in out + rec["hints"]]

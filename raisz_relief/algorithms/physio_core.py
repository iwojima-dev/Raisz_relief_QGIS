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
"""
physio_core -- the HYBRID render core (Hammond + Mower + Alpha) on the
shared v4 foundation.

Hammond classification splits the terrain into mountains/hills and
plains/valleys; mountains get fall lines on the displaced framework with
Mower-style cutoff, plains get variable-density stipple (Alpha). The fill
(hypsometric/thematic, draped), themed waters/roads/settlements and
clipping go through the shared grid/fills/theme/compose/overlays modules.
"""

from __future__ import annotations

import os
import numpy as np
from scipy import ndimage

from . import grid as gridmod
from . import fills, theme, compose


def smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def floating_horizon(disp, rows):
    ds = np.arange(rows)[:, None] - disp
    flip = ds[::-1]
    cummin = np.minimum.accumulate(flip, axis=0)
    prev = np.empty_like(cummin)
    prev[0] = np.inf
    prev[1:] = cummin[:-1]
    vis_flip = flip < prev - 1e-6
    return ndimage.binary_dilation(vis_flip[::-1], iterations=1)


def render_landform(
        dem_path, out_png, grid=None,
        interval=40.0, view_angle=40.0, vert_exag=2.2, base_scale_px=55,
        light_az=315.0, light_alt=45.0, smooth_sigma_px=1.6,
        hammond_window_m=3000.0, plain_lo=60.0, plain_hi=170.0,
        hammond_auto=True, hammond_p_lo=40.0, hammond_p_hi=85.0,
        max_width=1.9, slope_weight=0.45, min_draw_width=0.35, fall_spacing=4.0,
        stipple_r_px=4.0, dot_size=0.8,
        draw_framework=True, framework_on_plains=False,
        draw_fall=True, draw_stipple=True,
        overlays=None, fill_mode="none", palette="patterson", hypso_shade=0.35,
        override_min=None, override_max=None, stretch=False, fill_alpha=0.85,
        water_patterns=False,
        draw_baseline=True, baseline_level=0.5,
        valley_densify=True, densify_scale_m=2500.0,
        view_rot=0,
        auto_sea=False, sea_level=0.0, ink="#2a1d10", hand_jitter=0.0,
        sheet=None, bulk_shade=0.0, bulk_win=120, anag=0.0, anag_spacing=6,
        rel_scale=False, rel_target=12.0, rel_levels=12, rel_slopes=False,
        nodata_mode="plain", settle_font=None, settle_font_scale=1.0,
        max_px=2000, dpi=150, bg="#f4ecd6", progress=None):
    """Hybrid landform map with the decoration layer -> PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    overlays = overlays or {}

    def tick(p, m):
        if progress:
            progress(p, m)

    tick(3, "Reading and preparing the DEM...")
    if grid is None:
        grid = gridmod.working_grid(dem_path, max_px=max_px)
    z0, px, py, valid = gridmod.read_dem(dem_path, grid, nodata_mode, sea_level)
    geff = grid.geff
    if view_rot:
        z0, geff = gridmod.rotate_view(z0, geff, view_rot)
        valid = np.rot90(valid, int(view_rot) % 4)
        if view_rot % 2 == 1:
            px, py = py, px
    rows, cols = z0.shape
    if not valid.all():
        tick(4, "No data: %.1f%% of the frame, mode '%s'"
             % (100.0 * (~valid).mean(), nodata_mode))
        _nr = gridmod.nodata_polygons(valid, geff)
        if _nr:
            overlays = dict(overlays)
            # the nodata border is the same survey cut as the sheet frame
            overlays["nodata_edges"] = _nr
            if nodata_mode == "sea":
                overlays["sea_auto"] = list(overlays.get("sea_auto", [])) + _nr
    if auto_sea:
        _srings = gridmod.sea_polygons(z0, geff, sea_level)
        if _srings:
            overlays = dict(overlays)
            overlays["sea_auto"] = list(overlays.get("sea_auto", [])) + _srings
    z = ndimage.gaussian_filter(z0, sigma=smooth_sigma_px)

    tick(16, "Hammond classification...")
    win = int(max(3, round(hammond_window_m / ((px + py) / 2.0))))
    win = max(win, 12)          # pixel floor: keeps classification from blocking on coarse DEMs
    win = min(win, min(rows, cols) // 2)
    LR = ndimage.gaussian_filter(
        ndimage.maximum_filter(z0, size=win) - ndimage.minimum_filter(z0, size=win),
        sigma=max(win / 4.0, 1.0))
    if progress:
        pcs = np.nanpercentile(LR, [25, 50, 75, 90])
        progress(15, "DEM: local relief (m) P25/50/75/90 = "
                     "%.0f/%.0f/%.0f/%.0f -- a guide for manual thresholds"
                     % tuple(pcs))
    if hammond_auto:
        # Plains thresholds adapt DOWN to gentle terrain but are capped by
        # absolute ceilings: otherwise, in continuous high mountains the
        # "gentlest" percentiles are still steep slopes (hundreds of meters
        # of local relief) and auto mode would classify half the mountains
        # as plains. The lo ceiling prevents calling something a plain when
        # its local relief is clearly larger than that of hills.
        lo = float(np.clip(np.nanpercentile(LR, hammond_p_lo), 12.0, 50.0))
        hi = float(np.clip(np.nanpercentile(LR, hammond_p_hi), 40.0, 150.0))
        hi = max(hi, lo * 1.4)
        plain_lo, plain_hi = lo, hi
    w_plain = 1.0 - smoothstep(LR, plain_lo, plain_hi)
    w_relief = 1.0 - w_plain
    if progress:
        progress(18, f"Hammond: plains thresholds {plain_lo:.0f}/{plain_hi:.0f} m "
                     f"({'auto' if hammond_auto else 'manual'}), "
                     f"relief {np.mean(w_relief >= 0.4) * 100:.0f}% of area")

    tick(30, "Morphometry and illumination...")
    base = ndimage.grey_opening(z, size=(base_scale_px, base_scale_px))
    base = ndimage.gaussian_filter(base, sigma=base_scale_px / 3.0)
    base = np.minimum(base, z)
    relief = np.clip(z - base, 0, None)

    gyr, gxr = np.gradient(z, py, px)
    dzdN = -gyr; dzdE = gxr
    slope = np.degrees(np.arctan(np.hypot(dzdE, dzdN)))
    slope_ratio = np.clip(np.tan(np.radians(slope)), 0, 1)
    if rel_slopes:
        # percentile normalization over the relief zone: p95 of tan -> 1.0;
        # Hammond (LR) is untouched -- classification happens upstream
        _sr = slope_ratio[(w_relief >= 0.4) & (slope_ratio > 1e-4)]
        if _sr.size:
            _top = max(float(np.percentile(_sr, 95)), 1e-4)
            slope_ratio = np.clip(slope_ratio / _top, 0, 1)
            tick(31, "Relative slopes: p95(tan)=%.3f -> 1.0" % _top)
    az, alt = np.radians(light_az), np.radians(light_alt)
    lx, ly, lz = np.sin(az) * np.cos(alt), np.cos(az) * np.cos(alt), np.sin(alt)
    nrm = np.sqrt(dzdE ** 2 + dzdN ** 2 + 1)
    illum = np.clip((-dzdE * lx - dzdN * ly + lz) / nrm, -1, 1)
    v = (illum + 1) / 2.0

    shear = vert_exag / np.tan(np.radians(view_angle))
    disp = (relief * shear / py) * w_relief
    if rel_scale:
        # normalize the FINAL disp (after w_relief) -- Hammond does not see it
        disp *= gridmod.rel_scale_k(disp, rows, rel_target, vert_exag,
                                    log=lambda m: tick(32, m))
        interval = gridmod.rel_interval(float(z0.min()), float(z0.max()),
                                        rel_levels, log=lambda m: tick(32, m))

    tick(42, "Hidden-line removal...")
    vis = floating_horizon(disp, rows)
    if nodata_mode == "paper":
        # 'paper': no strokes, no framework, no plains stipple outside data
        vis = vis & valid
        w_plain = w_plain * valid
        w_relief = w_relief * valid

    def smp(a, r, c):
        return ndimage.map_coordinates(
            a, [np.atleast_1d(r), np.atleast_1d(c)], order=1, mode="nearest")

    def vis_at(r, c):
        rr = np.clip(np.round(r).astype(int), 0, rows - 1)
        cc = np.clip(np.round(c).astype(int), 0, cols - 1)
        return vis[rr, cc]

    fig, ax = plt.subplots(figsize=(cols / 90, rows / 90), dpi=dpi)
    fig.patch.set_facecolor(bg); ax.set_facecolor(bg)

    # --- base fill (hypsometric/thematic, draped) ---
    tick(48, "Relief fill...")
    img, extent = fills.build_base_fill(
        fill_mode, z0, disp, illum, grid, palette=palette, shade=hypso_shade,
        override_min=override_min, override_max=override_max, stretch=stretch,
        thematic_polys=overlays.get("thematic"), alpha=fill_alpha,
        geff_rot=(geff if view_rot else None),
        bulk_shade=bulk_shade, bulk_win=bulk_win, light_az=light_az, ink=ink,
        valid=(valid if nodata_mode == "paper" else None))
    compose.blit_fill(ax, img, extent, z=1)
    if anag > 0.0:
        from . import engrave
        engrave.draw_anaglypt(ax, disp, illum, ink,
                              spacing=anag_spacing, density=anag, z=1.8)

    styles = theme.resolve(theme.background_of(fill_mode), paper=bg, ink=ink)
    from . import sheet as sheetmod
    styles = sheetmod.apply_settle_style(styles, rows, cols,
                                         settle_font, settle_font_scale)
    ink_rgb = theme._hexrgb(ink)           # stroke color (paper presets)
    _mpp = (px + py) / 2.0                 # physical pixel size (rotation-invariant)
    pat = (dict(enable=True, vignette_step=6 * _mpp, vignette_n=3,
                hatch_spacing=7 * _mpp, marsh_spacing=14 * _mpp,
                extent=grid.extent)
           if water_patterns else None)
    n_area = compose.draw_area_waters(ax, overlays, geff, disp, styles,
                                      z0=6, pat=pat)
    lcpat = dict(forest=7 * _mpp, sand=5 * _mpp, ice=6 * _mpp,
                 scrub=11 * _mpp, grass=9 * _mpp)
    compose.draw_landcover(ax, overlays, geff, disp, styles, lcpat,
                           z0=4.5, vis=vis)

    levels = np.arange(np.floor(z.min() / interval) * interval,
                       z.max() + interval, interval)
    cs = ax.contour(np.arange(cols), np.arange(rows), z, levels=levels)
    contour_paths = [seg for segs in cs.allsegs for seg in segs if len(seg) >= 2]
    cs.remove()

    # --- valley/plains stipple (variable density) ---
    n_stipple = 0
    if draw_stipple:
        tick(54, "Plains stipple texture...")
        if valley_densify:
            dist = ndimage.distance_transform_edt(w_relief < 0.5)
            Dpx = max(densify_scale_m / ((px + py) / 2.0), 1.0)
            r_local = stipple_r_px * (0.5 + 0.5 * smoothstep(dist, 0, Dpx))
            r_min = stipple_r_px * 0.5
        else:
            r_local = np.full((rows, cols), stipple_r_px)
            r_min = stipple_r_px
        # fast jittered grid (vectorized) instead of the slow
        # Poisson sampling: same speckle, no Python loop and no O(N^2)
        jrng = np.random.RandomState(13)
        nxs = max(int(round(cols / r_min)), 1)
        nys = max(int(round(rows / r_min)), 1)
        sx = cols / nxs; sy = rows / nys
        GX, GY = np.meshgrid((np.arange(nxs) + 0.5) * sx,
                             (np.arange(nys) + 0.5) * sy)
        cx = (GX + (jrng.rand(*GX.shape) - 0.5) * sx).ravel()
        cy = (GY + (jrng.rand(*GY.shape) - 0.5) * sy).ravel()
        cand = np.column_stack([cx, cy])
        cand = cand[(cand[:, 0] >= 0) & (cand[:, 0] < cols) &
                    (cand[:, 1] >= 0) & (cand[:, 1] < rows)]
        v_smooth = ndimage.gaussian_filter(v, sigma=6)
        if len(cand):
            wp = smp(w_plain, cand[:, 1], cand[:, 0])
            rl = smp(r_local, cand[:, 1], cand[:, 0])
            rng = np.random.RandomState(7)
            keep = (wp >= 0.50) & (rng.uniform(size=len(cand)) < (r_min / rl) ** 2)
            cand = cand[keep]; wp = wp[keep]; rl = rl[keep]
            # scatter guard on huge plains: cap the number of dots
            STIPPLE_MAX = 400000
            if len(cand) > STIPPLE_MAX:
                sel = rng.choice(len(cand), STIPPLE_MAX, replace=False)
                cand = cand[sel]; wp = wp[sel]; rl = rl[sel]
        if len(cand):
            vh = smp(v_smooth, cand[:, 1], cand[:, 0])
            dens = np.clip(r_min / rl, 0.4, 1.0)
            ssz = dot_size * (1.0 - 0.25 * (vh - 0.5)) * (0.6 + 0.4 * dens)
            salpha = 0.85 * smoothstep(wp, 0.50, 0.70)
            ax.scatter(cand[:, 0], cand[:, 1], s=np.clip(ssz, 0.15, 3) ** 2,
                       c=ink, alpha=np.clip(salpha, 0.1, 0.9),
                       linewidths=0, marker="o", zorder=3)
            n_stipple = len(cand)

    # --- gray framework ---
    n_frame = 0
    if draw_framework:
        tick(64, "Displaced contours (framework)...")
        frame_list = []
        for seg in contour_paths:
            c_idx = seg[:, 0]; r_idx = seg[:, 1]
            r_new = r_idx - smp(disp, r_idx, c_idx)
            vv = vis_at(r_idx, c_idx)
            wr = (np.ones_like(c_idx) if framework_on_plains
                  else smp(w_relief, r_idx, c_idx))
            sg = smp(slope_ratio, r_idx, c_idx)
            keep = vv & (wr >= 0.55) & (sg >= 0.10)
            pair = keep[:-1] & keep[1:]
            if pair.any():
                p0 = np.column_stack([c_idx[:-1], r_new[:-1]])[pair]
                p1 = np.column_stack([c_idx[1:], r_new[1:]])[pair]
                frame_list.append(np.stack([p0, p1], axis=1))
        if frame_list:
            frame_segs = np.concatenate(frame_list)
            n_frame = len(frame_segs)
            ax.add_collection(LineCollection(
                frame_segs, linewidths=0.3, colors=[(*ink_rgb, 0.4)],
                zorder=4))

    # --- fall lines (mountains/hills) ---
    n_fall = 0
    if draw_fall:
        tick(74, "Tracing fall lines...")
        max_steps = 28

        def trace_fall(r0, c0, drop_limit):
            pts = [(r0, c0)]; r, c = r0, c0; z0v = float(smp(z, r0, c0)[0])
            for _ in range(max_steps):
                gE = float(smp(dzdE, r, c)[0]); gN = float(smp(dzdN, r, c)[0])
                dr, dc = +gN, -gE; n = np.hypot(dr, dc)
                if n < 1e-6:
                    break
                r += dr / n * 1.2; c += dc / n * 1.2
                if not (0 <= r < rows and 0 <= c < cols):
                    break
                pts.append((r, c))
                if z0v - float(smp(z, r, c)[0]) >= drop_limit:
                    break
            return np.array(pts)

        seg_list, lw_list, col_list, seed_list = [], [], [], []
        jrng2 = np.random.RandomState(99)   # hand jitter (deterministic)
        for k, seg in enumerate(contour_paths):
            if progress and k % 80 == 0:
                tick(74 + int(14 * k / max(len(contour_paths), 1)),
                     "Tracing fall lines...")
            c_idx = seg[:, 0]; r_idx = seg[:, 1]
            dlen = np.r_[0, np.cumsum(np.hypot(np.diff(c_idx), np.diff(r_idx)))]
            s = 0.0
            while s < dlen[-1]:
                ci = float(np.interp(s, dlen, c_idx))
                ri = float(np.interp(s, dlen, r_idx))
                wr = float(smp(w_relief, [ri], [ci])[0])
                sr = float(smp(slope_ratio, [ri], [ci])[0])
                vv = float(smp(v, [ri], [ci])[0])
                s += max(fall_spacing * (1.0 - 0.5 * (1 - vv)) * (1.0 - 0.3 * sr),
                         fall_spacing * 0.3)
                if wr < 0.5:        # strokes begin where the stipple ends
                    continue
                W = (sr * max_width * slope_weight
                     + (1.0 - vv) * max_width * (1.0 - slope_weight)) * wr
                if W < min_draw_width:
                    continue
                drop_limit = interval * (1.0 + 1.4 * max(0.0, (0.66 - wr) / 0.16))
                fall = trace_fall(ri, ci, drop_limit)
                if len(fall) < 2:
                    continue
                r_new = fall[:, 0] - smp(disp, fall[:, 0], fall[:, 1])
                vmask = vis_at(fall[:, 0], fall[:, 1])
                pair = vmask[:-1] & vmask[1:]
                if not pair.any():
                    continue
                p0 = np.column_stack([fall[:-1, 1], r_new[:-1]])[pair]
                p1 = np.column_stack([fall[1:, 1], r_new[1:]])[pair]
                arr = np.stack([p0, p1], axis=1)
                seg_list.append(arr)
                seed_list.append((ci, ri))
                if hand_jitter > 0 and len(fall) >= 2:
                    tt = np.linspace(0.0, 1.0, len(fall))
                    prof = 1.0 - hand_jitter * 0.55 * (1.0 - np.sin(np.pi * tt))
                    prof *= 1.0 + hand_jitter * 0.3 * (jrng2.rand(len(fall)) - 0.5) * 2.0
                    wseg = (W * 0.5 * (prof[:-1] + prof[1:]))[pair]
                    lw_list.append(np.clip(wseg, min_draw_width * 0.4, None))
                else:
                    lw_list.append(np.full(len(arr), W))
                a = min(0.45 + 0.5 * (1 - vv), 0.95)
                col_list.append(np.tile([*ink_rgb, a], (len(arr), 1)))
        if len(seg_list) > 4:
            # drop lonely strokes: fewer than 2 neighbors within the radius
            from scipy.spatial import cKDTree
            _pts = np.array(seed_list)
            _cnt = cKDTree(_pts).query_ball_point(
                _pts, r=fall_spacing * 4.0, return_length=True)
            _keep = _cnt >= 3
            if _keep.any() and not _keep.all():
                _idx = np.nonzero(_keep)[0]
                seg_list = [seg_list[i] for i in _idx]
                lw_list = [lw_list[i] for i in _idx]
                col_list = [col_list[i] for i in _idx]
        if seg_list:
            fall_segs = np.concatenate(seg_list)
            n_fall = len(fall_segs)
            ax.add_collection(LineCollection(
                fall_segs, linewidths=np.concatenate(lw_list),
                colors=np.concatenate(col_list), capstyle="round", zorder=5))

    # --- mountain-foot baseline (dotline) ---
    n_base = 0
    if draw_baseline:
        tick(89, "Outlining mountain feet...")
        wr_s = ndimage.gaussian_filter(w_relief, sigma=2.0)
        csb = ax.contour(np.arange(cols), np.arange(rows), wr_s,
                         levels=[baseline_level])
        base_paths = [s for segs in csb.allsegs for s in segs if len(s) >= 2]
        csb.remove()
        bsegs = []
        for seg in base_paths:
            c_idx = seg[:, 0]; r_idx = seg[:, 1]
            r_new = r_idx - smp(disp, r_idx, c_idx)
            bsegs.append(np.column_stack([c_idx, r_new]))
        if bsegs:
            n_base = len(bsegs)
            bs = styles["baseline"]
            ax.add_collection(LineCollection(
                bsegs, linewidths=bs["lw"], colors=[bs["color"]],
                alpha=bs["alpha"], linestyles=(0, (1, 2.5)), zorder=5))

    # --- rivers, roads, point settlements (themed, clipped behind mountains) ---
    n_inf = compose.draw_infrastructure(ax, overlays, geff, disp, styles,
                                        vis=vis, z0=7)

    tick(95, "Saving output...")
    disp_max = float(disp.max())
    # silhouette: per-column minimum screen Y -- breaks the top frame line
    top_profile = (np.arange(rows)[:, None] - disp).min(axis=0)
    margin = 0.04 * max(rows, cols)
    n_sheet = {}
    if sheet:
        from . import sheet as sheetmod
        n_sheet = sheetmod.draw_sheet(
            ax, geff, grid.proj, rows, cols, margin, bg, ink, sheet,
            top_pad=disp_max,
            extras=dict(styles=styles, overlays=overlays, fall=draw_fall,
                        stipple=draw_stipple, auto_sea=auto_sea),
            log=lambda m: tick(94, m), top_profile=top_profile)
    ax.set_xlim(-margin, cols + margin)
    ax.set_ylim(rows + margin, -disp_max - margin)
    ax.set_aspect("equal"); ax.axis("off")
    plt.subplots_adjust(0, 0, 1, 1)
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    plt.savefig(out_png, dpi=dpi, facecolor=fig.get_facecolor(),
                bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
    if sheet and sheet.get("misreg", 0) > 0:
        from . import print_fx
        print_fx.misregister(out_png, sheet["misreg"],
                             log=lambda m: tick(99, m))
    tick(100, "Done.")
    stats = dict(rows=rows, cols=cols, scale=grid.scale, window_px=win,
                 levels=len(levels), stipple=n_stipple, frame_segs=n_frame,
                 fall_segs=n_fall, plain_frac=float(np.mean(w_plain)),
                 plain_lo=float(plain_lo), plain_hi=float(plain_hi),
                 max_disp_px=disp_max, baseline=n_base)
    stats.update(n_area); stats.update(n_inf); stats.update(n_sheet)
    return stats

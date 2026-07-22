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
classic_core -- the CLASSIC render core (Alpha & Winter 1971; Raisz 1931;
Ridd 1963).

Full DEM resolution, uniform physiographic hachuring over the whole
surface (no Hammond classification, no stippled plains) -- the original
engraved look. The floating horizon is vectorized (unlike the legacy
double-loop version). Decoration (fill/waters/roads/settlements, clipping,
draping) comes from the shared v4 modules.

Memory is not limited by resampling here -- the estimate and the limit
are handled by the calling algorithm.
"""

from __future__ import annotations

import os
import numpy as np
from scipy import ndimage

from . import grid as gridmod
from . import fills, theme, compose
from .physio_core import floating_horizon


def render_classic(
        dem_path, out_png, grid=None,
        interval=40.0, view_angle=40.0, vert_exag=2.2, base_scale_px=55,
        light_az=315.0, light_alt=45.0,
        fall_spacing=4.0, shadow_density=0.8, light_skip=0.75, min_slope_deg=4.0,
        draw_framework=True, draw_fall=True,
        overlays=None, fill_mode="none", palette="patterson", hypso_shade=0.35,
        override_min=None, override_max=None, stretch=False, fill_alpha=0.85,
        water_patterns=False,
        view_rot=0,
        auto_sea=False, sea_level=0.0, ink="#2a1d10", hand_jitter=0.0,
        sheet=None, bulk_shade=0.0, bulk_win=120, anag=0.0, anag_spacing=6,
        rel_scale=False, rel_target=12.0, rel_levels=12, rel_slopes=False,
        nodata_mode="plain",
        dpi=150, bg="#f4ecd6", progress=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    overlays = overlays or {}

    def tick(p, m):
        if progress:
            progress(p, m)

    tick(2, "Reading DEM (full resolution)...")
    if grid is None:
        grid = gridmod.working_grid(dem_path, max_px=None)
    z, px, py, valid = gridmod.read_dem(dem_path, grid, nodata_mode, sea_level)
    geff = grid.geff
    if view_rot:
        z, geff = gridmod.rotate_view(z, geff, view_rot)
        valid = np.rot90(valid, int(view_rot) % 4)
        if view_rot % 2 == 1:
            px, py = py, px
    rows, cols = z.shape
    if not valid.all():
        tick(4, "No data: %.1f%% of the frame, mode '%s'"
             % (100.0 * (~valid).mean(), nodata_mode))
        _nr = gridmod.nodata_polygons(valid, geff)
        if _nr:
            overlays = dict(overlays)
            # the nodata border is the same survey cut as the sheet frame:
            # no coastal band along it
            overlays["nodata_edges"] = _nr
            if nodata_mode == "sea":
                overlays["sea_auto"] = list(overlays.get("sea_auto", [])) + _nr
    if auto_sea:
        _srings = gridmod.sea_polygons(z, geff, sea_level)
        if _srings:
            overlays = dict(overlays)
            overlays["sea_auto"] = list(overlays.get("sea_auto", [])) + _srings

    tick(12, "Local basis and morphometry...")
    base = ndimage.grey_opening(z, size=(base_scale_px, base_scale_px))
    base = ndimage.gaussian_filter(base, sigma=base_scale_px / 3.0)
    base = np.minimum(base, z)
    relief = np.clip(z - base, 0, None)
    gyr, gxr = np.gradient(z, py, px)
    dzdN = -gyr; dzdE = gxr
    slope = np.degrees(np.arctan(np.hypot(dzdE, dzdN)))
    slope_norm_deg, min_slope_eff = 45.0, min_slope_deg
    if rel_slopes:
        min_slope_eff, slope_norm_deg = gridmod.rel_slope_norm(
            slope, log=lambda m: tick(13, m))
    slope_n = np.clip(slope / slope_norm_deg, 0, 1)
    az, alt = np.radians(light_az), np.radians(light_alt)
    lx, ly, lz = np.sin(az) * np.cos(alt), np.cos(az) * np.cos(alt), np.sin(alt)
    nrm = np.sqrt(dzdE ** 2 + dzdN ** 2 + 1)
    illum = (-dzdE * lx - dzdN * ly + lz) / nrm
    darkness = np.clip(0.5 - 0.5 * illum, 0, 1)

    shear = vert_exag / np.tan(np.radians(view_angle))
    disp = relief * shear / py
    if rel_scale:
        disp *= gridmod.rel_scale_k(disp, rows, rel_target, vert_exag,
                                    log=lambda m: tick(14, m))
        interval = gridmod.rel_interval(float(z.min()), float(z.max()),
                                        rel_levels, log=lambda m: tick(14, m))

    tick(30, "Hidden-line removal (floating horizon)...")
    vis = floating_horizon(disp, rows)
    if nodata_mode == "paper":
        # 'paper' mode: no strokes, no framework, no decoration outside
        # the data -- vis gates everything that is clipped by visibility
        vis = vis & valid

    def smp(a, r, c):
        return ndimage.map_coordinates(
            a, [np.atleast_1d(r), np.atleast_1d(c)], order=1, mode="nearest")

    def vis_at(r, c):
        rr = np.clip(np.round(r).astype(int), 0, rows - 1)
        cc = np.clip(np.round(c).astype(int), 0, cols - 1)
        return vis[rr, cc]

    def displace_clip(c_idx, r_idx):
        r_new = r_idx - smp(disp, r_idx, c_idx)
        vv = vis_at(r_idx, c_idx)
        pair = vv[:-1] & vv[1:]
        out = []
        for i in np.nonzero(pair)[0]:
            out.append(([c_idx[i], r_new[i]], [c_idx[i + 1], r_new[i + 1]]))
        return out

    fig, ax = plt.subplots(figsize=(cols / 90, rows / 90), dpi=dpi)
    fig.patch.set_facecolor(bg); ax.set_facecolor(bg)

    tick(42, "Relief fill...")
    img, extent = fills.build_base_fill(
        fill_mode, z, disp, illum, grid, palette=palette, shade=hypso_shade,
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

    tick(48, "Contours (framework)...")
    levels = np.arange(np.floor(z.min() / interval) * interval,
                       z.max() + interval, interval)
    cs = ax.contour(np.arange(cols), np.arange(rows), z, levels=levels)
    contour_paths = [seg for segs in cs.allsegs for seg in segs if len(seg) >= 2]
    cs.remove()

    n_frame = 0
    if draw_framework:
        tick(55, "Displaced contours...")
        frame_segs = []
        for seg in contour_paths:
            frame_segs += displace_clip(seg[:, 0], seg[:, 1])
        n_frame = len(frame_segs)
        ax.add_collection(LineCollection(
            frame_segs, linewidths=0.35, colors=[(*ink_rgb, 0.45)],
            zorder=4))

    max_steps = int(np.clip(interval / max(np.tan(np.radians(
        max(min_slope_eff, 0.5))) * ((px + py) / 2.0), 1e-3), 4, 40))

    def trace_fall(r0, c0):
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
            if z0v - float(smp(z, r, c)[0]) >= interval:
                break
        return np.array(pts)

    n_fall = 0
    if draw_fall:
        tick(65, "Tracing fall lines...")
        seg_list, lw_list, col_list = [], [], []
        jrng2 = np.random.RandomState(99)   # hand jitter (deterministic)
        for k, seg in enumerate(contour_paths):
            if progress and k % 50 == 0:
                tick(65 + int(25 * k / max(len(contour_paths), 1)),
                     "Tracing fall lines...")
            c_idx = seg[:, 0]; r_idx = seg[:, 1]
            dlen = np.r_[0, np.cumsum(np.hypot(np.diff(c_idx), np.diff(r_idx)))]
            s = 0.0
            while s < dlen[-1]:
                ci = float(np.interp(s, dlen, c_idx))
                ri = float(np.interp(s, dlen, r_idx))
                dk = float(smp(darkness, [ri], [ci])[0])
                sl = float(smp(slope_n, [ri], [ci])[0])
                il = float(smp(illum, [ri], [ci])[0])
                s += max(fall_spacing * (1.0 - shadow_density * 0.7 * dk) *
                         (1.0 - 0.3 * sl), fall_spacing * 0.25)
                if sl * slope_norm_deg < min_slope_eff or il > light_skip:
                    continue
                fall = trace_fall(ri, ci)
                if len(fall) < 2:
                    continue
                segs = displace_clip(fall[:, 1], fall[:, 0])
                if not segs:
                    continue
                arr = np.array(segs)
                seg_list.append(arr)
                Wc = 0.3 + 1.6 * sl * (0.3 + 0.7 * dk)
                M = len(arr)
                if hand_jitter > 0 and M >= 2:
                    tt = np.linspace(0.0, 1.0, M)
                    prof = 1.0 - hand_jitter * 0.55 * (1.0 - np.sin(np.pi * tt))
                    prof *= 1.0 + hand_jitter * 0.3 * (jrng2.rand(M) - 0.5) * 2.0
                    lw_list.append(np.clip(Wc * prof, 0.05, None))
                else:
                    lw_list.append(np.full(M, Wc))
                a = min(0.45 + 0.5 * dk, 0.95)
                col_list.append(np.tile([*ink_rgb, a], (len(arr), 1)))
        if seg_list:
            fall_segs = np.concatenate(seg_list)
            n_fall = len(fall_segs)
            ax.add_collection(LineCollection(
                fall_segs, linewidths=np.concatenate(lw_list),
                colors=np.concatenate(col_list), capstyle="round", zorder=5))

    n_inf = compose.draw_infrastructure(ax, overlays, geff, disp, styles,
                                        vis=vis, z0=7)

    tick(94, "Saving output...")
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
            extras=dict(styles=styles, overlays=overlays,
                        fall=draw_fall, stipple=False, auto_sea=auto_sea),
            log=lambda m: tick(93, m), top_profile=top_profile)
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
    stats = dict(rows=rows, cols=cols, levels=len(levels),
                 frame_segs=n_frame, fall_segs=n_fall, max_disp_px=disp_max)
    stats.update(n_area); stats.update(n_inf); stats.update(n_sheet)
    return stats

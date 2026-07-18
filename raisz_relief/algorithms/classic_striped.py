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
classic_striped -- strip-tiling of the CLASSIC mode for large sheets
without memory overflow.

The idea (variant B -- vector accumulation):
  * The fill and decoration are computed once on a DOWNSAMPLED grid
    (cheap, seamless) and stretched into full-sheet coordinates.
  * Hachures (fall lines) and the framework are computed in STRIPS at
    FULL resolution, bottom-up (from the observer), carrying the floating
    horizon state between strips. Full-size DEM arrays are never held in
    memory -- only the current strip with its pad.
  * All vector segments accumulate in sheet coordinates and are drawn
    once.

Local operations (grey_opening basis, gradients, stroke tracing) stay
correct inside the strip core thanks to the vertical PAD. The only
column-global operation -- the floating horizon -- is carried between
strips as a per-column running minimum of screen Y.

View rotation is not applied in strip mode yet.
"""

from __future__ import annotations

import os
import numpy as np
from scipy import ndimage

from . import grid as gridmod
from . import fills, theme, compose


def _morphometry(zt, px, py, base_scale_px, light_az, light_alt,
                 vert_exag, view_angle, disp_scale=1.0, slope_norm_deg=45.0):
    """Strip morphometry (as in classic_core). Returns a dict of arrays.
    disp_scale/slope_norm_deg are the relative-mode coefficients: they are
    computed ONCE on the downsampled pass and passed into every strip, so
    strips cannot normalize differently and split at the seams."""
    base = ndimage.grey_opening(zt, size=(base_scale_px, base_scale_px))
    base = ndimage.gaussian_filter(base, sigma=base_scale_px / 3.0)
    base = np.minimum(base, zt)
    relief = np.clip(zt - base, 0, None)
    gyr, gxr = np.gradient(zt, py, px)
    dzdN = -gyr; dzdE = gxr
    slope = np.degrees(np.arctan(np.hypot(dzdE, dzdN)))
    slope_n = np.clip(slope / slope_norm_deg, 0, 1)
    az, alt = np.radians(light_az), np.radians(light_alt)
    lx, ly, lz = np.sin(az) * np.cos(alt), np.cos(az) * np.cos(alt), np.sin(alt)
    nrm = np.sqrt(dzdE ** 2 + dzdN ** 2 + 1)
    illum = (-dzdE * lx - dzdN * ly + lz) / nrm
    darkness = np.clip(0.5 - 0.5 * illum, 0, 1)
    shear = vert_exag / np.tan(np.radians(view_angle))
    disp = relief * shear / py * disp_scale
    return dict(dzdN=dzdN, dzdE=dzdE, slope_n=slope_n, illum=illum,
                darkness=darkness, disp=disp, slope=slope)


def render_classic_striped(
        dem_path, out_png, grid=None,
        interval=40.0, view_angle=40.0, vert_exag=2.2, base_scale_px=55,
        light_az=315.0, light_alt=45.0,
        fall_spacing=4.0, shadow_density=0.8, light_skip=0.75, min_slope_deg=4.0,
        draw_framework=True, draw_fall=True,
        fill_mode="none", palette="patterson", hypso_shade=0.35,
        override_min=None, override_max=None, stretch=False, fill_alpha=0.85,
        ink="#2a1d10", hand_jitter=0.0,
        overlays=None, water_patterns=False, auto_sea=False, sea_level=0.0,
        strip_rows=2048, fill_max_px=2500, sheet=None,
        bulk_shade=0.0, bulk_win=120, anag=0.0, anag_spacing=6,
        rel_scale=False, rel_target=12.0, rel_levels=12, rel_slopes=False,
        dpi=150, bg="#f4ecd6", progress=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    def tick(p, m):
        if progress:
            progress(p, m)

    tick(2, "Strip mode: preparing the grid...")
    if grid is None:
        grid = gridmod.working_grid(dem_path, max_px=None)
    R, C = grid.ny, grid.nx
    px = abs(grid.geff[1]); py = abs(grid.geff[5])
    ink_rgb = theme._hexrgb(ink)
    shear = vert_exag / np.tan(np.radians(view_angle))

    fig, ax = plt.subplots(figsize=(C / 90, R / 90), dpi=dpi)
    fig.patch.set_facecolor(bg); ax.set_facecolor(bg)

    # -- downsampled pass: fill + global min/max for contour levels --
    tick(8, "Downsampled fill...")
    g_ds = gridmod.working_grid(dem_path, max_px=fill_max_px)
    z_ds, pxd, pyd = gridmod.read_dem(dem_path, g_ds)
    m_ds = _morphometry(z_ds, pxd, pyd, base_scale_px, light_az, light_alt,
                        vert_exag, view_angle)
    disp_ds = m_ds["disp"]                    # downsampled disp for decoration
    zmin, zmax = float(z_ds.min()), float(z_ds.max())
    # -- relative mode: GLOBAL coefficients from the downsampled pass
    #    (k is dimensionless and identical for the ds and full grids:
    #    target/ny and p99(disp) scale with the pixel the same way) --
    k_rel = 1.0
    slope_norm_deg, min_slope_eff = 45.0, min_slope_deg
    if rel_scale:
        k_rel = gridmod.rel_scale_k(disp_ds, g_ds.ny, rel_target, vert_exag,
                                    log=lambda m: tick(9, m))
        disp_ds *= k_rel
        interval = gridmod.rel_interval(zmin, zmax, rel_levels,
                                        log=lambda m: tick(9, m))
    if rel_slopes:
        min_slope_eff, slope_norm_deg = gridmod.rel_slope_norm(
            m_ds["slope"], log=lambda m: tick(9, m))
    if fill_mode != "none" or bulk_shade > 0.0:
        # shadow window is in full-raster px -> scale to the downsample
        win_ds = max(5, int(round(bulk_win * g_ds.ny / float(R))))
        img, ext = fills.build_base_fill(
            fill_mode, z_ds, disp_ds, m_ds["illum"], g_ds,
            palette=palette, shade=hypso_shade, override_min=override_min,
            override_max=override_max, stretch=stretch, alpha=fill_alpha,
            bulk_shade=bulk_shade, bulk_win=win_ds, light_az=light_az,
            ink=ink)
        if img is not None:
            sy = R / float(g_ds.ny)
            ext_full = (0, C, ext[2] * sy, ext[3] * sy)
            compose.blit_fill(ax, img, ext_full, z=1)
    if anag > 0.0:
        # engraving on the downsampled grid, coordinates in full size
        from . import engrave
        sp_ds = max(1, int(round(anag_spacing * g_ds.ny / float(R))))
        engrave.draw_anaglypt(ax, disp_ds, m_ds["illum"], ink,
                              spacing=sp_ds, density=anag, z=1.8,
                              scale=(C / float(g_ds.nx), R / float(g_ds.ny)))
    del m_ds                                  # keep z_ds, disp_ds for decoration

    levels = np.arange(np.floor(zmin / interval) * interval,
                       zmax + interval, interval)
    max_reach = 40 * 1.3
    pad = int(base_scale_px * 2 + max_reach + 8)

    max_steps = int(np.clip(interval / max(np.tan(np.radians(
        max(min_slope_eff, 0.5))) * ((px + py) / 2.0), 1e-3), 4, 40))
    jr = np.random.RandomState(99)
    carried = np.full(C, np.inf)
    fall_seg, fall_lw, fall_col, frame_seg = [], [], [], []
    disp_max_g = 0.0
    n_fall = n_frame = 0

    starts = list(range(0, R, strip_rows))
    for si, r0 in enumerate(reversed(starts)):
        r1 = min(r0 + strip_rows, R)
        tick(15 + int(78 * si / max(len(starts), 1)),
             "Strip %d/%d..." % (si + 1, len(starts)))
        pr0 = max(0, r0 - pad); pr1 = min(R, r1 + pad)
        zt = gridmod.read_dem_window(dem_path, grid, pr0, pr1)
        if zt.shape[0] < 2:
            continue
        M = _morphometry(zt, px, py, base_scale_px, light_az, light_alt,
                         vert_exag, view_angle,
                         disp_scale=k_rel, slope_norm_deg=slope_norm_deg)
        disp_t = M["disp"]; dzdE = M["dzdE"]; dzdN = M["dzdN"]
        slope_n = M["slope_n"]; illum = M["illum"]; darkness = M["darkness"]
        Ht = zt.shape[0]
        disp_max_g = max(disp_max_g, float(disp_t.max()))

        # floating horizon over the CORE [r0,r1) with carried state (bottom-up)
        lo = r0 - pr0; hi = r1 - pr0                 # local core indices
        core_disp = disp_t[lo:hi]
        Hc = hi - lo
        grc = (r0 + np.arange(Hc))[:, None]
        screen_c = grc - core_disp
        flip = screen_c[::-1]
        extv = np.vstack([carried[None, :], flip])
        cummin = np.minimum.accumulate(extv, axis=0)
        prev = cummin[:-1]
        vis_core = (flip < prev - 1e-6)[::-1]
        vis_core = ndimage.binary_dilation(vis_core, iterations=1)
        carried = cummin[-1].copy()                  # min over rows >= r0

        def smp(a, r_loc, c):
            return ndimage.map_coordinates(
                a, [np.atleast_1d(r_loc), np.atleast_1d(c)],
                order=1, mode="nearest")

        def vis_at(gr, c):
            cc = np.clip(np.round(c).astype(int), 0, C - 1)
            gg = np.round(gr).astype(int)
            inb = (gg >= r0) & (gg < r1)
            out = np.ones(len(gg), bool)
            k = np.clip(gg - r0, 0, Hc - 1)
            out[inb] = vis_core[k[inb], cc[inb]]
            return out

        def displace_clip(c_idx, gr_idx, core_only=False):
            r_loc = gr_idx - pr0
            r_new = gr_idx - smp(disp_t, r_loc, c_idx)
            vv = vis_at(gr_idx, c_idx)
            if core_only:
                vv = vv & (gr_idx >= r0) & (gr_idx < r1)
            pair = vv[:-1] & vv[1:]
            out = []
            for i in np.nonzero(pair)[0]:
                out.append(([c_idx[i], r_new[i]], [c_idx[i + 1], r_new[i + 1]]))
            return out

        # strip contours in GLOBAL rows
        cs = ax.contour(np.arange(C), pr0 + np.arange(Ht), zt, levels=levels)
        cpaths = [s for segs in cs.allsegs for s in segs if len(s) >= 2]
        cs.remove()

        if draw_framework:
            for seg in cpaths:
                for a, b in displace_clip(seg[:, 0], seg[:, 1], core_only=True):
                    frame_seg.append((a, b))

        if draw_fall:
            def trace_fall(gr0, c0):
                pts = [(gr0, c0)]; r, c = gr0, c0
                z0v = float(smp(zt, r - pr0, c0)[0])
                for _ in range(max_steps):
                    gE = float(smp(dzdE, r - pr0, c)[0])
                    gN = float(smp(dzdN, r - pr0, c)[0])
                    dr, dc = +gN, -gE; nn = np.hypot(dr, dc)
                    if nn < 1e-6:
                        break
                    r += dr / nn * 1.2; c += dc / nn * 1.2
                    if not (pr0 <= r < pr1 and 0 <= c < C):
                        break
                    pts.append((r, c))
                    if z0v - float(smp(zt, r - pr0, c)[0]) >= interval:
                        break
                return np.array(pts)

            for seg in cpaths:
                cc = seg[:, 0]; grr = seg[:, 1]
                dlen = np.r_[0, np.cumsum(np.hypot(np.diff(cc), np.diff(grr)))]
                s = 0.0
                while s < dlen[-1]:
                    ci = float(np.interp(s, dlen, cc))
                    gri = float(np.interp(s, dlen, grr))
                    dk = float(smp(darkness, gri - pr0, ci)[0])
                    sl = float(smp(slope_n, gri - pr0, ci)[0])
                    il = float(smp(illum, gri - pr0, ci)[0])
                    s += max(fall_spacing * (1.0 - shadow_density * 0.7 * dk) *
                             (1.0 - 0.3 * sl), fall_spacing * 0.25)
                    if not (r0 <= gri < r1):          # seed only inside the strip core
                        continue
                    if sl * slope_norm_deg < min_slope_eff or il > light_skip:
                        continue
                    fall = trace_fall(gri, ci)
                    if len(fall) < 2:
                        continue
                    segs = displace_clip(fall[:, 1], fall[:, 0])
                    if not segs:
                        continue
                    arr = np.array(segs)
                    fall_seg.append(arr)
                    Wc = 0.3 + 1.6 * sl * (0.3 + 0.7 * dk)
                    K = len(arr)
                    if hand_jitter > 0 and K >= 2:
                        tt = np.linspace(0.0, 1.0, K)
                        prof = 1.0 - hand_jitter * 0.55 * (1.0 - np.sin(np.pi * tt))
                        prof *= 1.0 + hand_jitter * 0.3 * (jr.rand(K) - 0.5) * 2.0
                        fall_lw.append(np.clip(Wc * prof, 0.05, None))
                    else:
                        fall_lw.append(np.full(K, Wc))
                    a = min(0.45 + 0.5 * dk, 0.95)
                    fall_col.append(np.tile([*ink_rgb, a], (K, 1)))
        del zt, M, disp_t, dzdE, dzdN, slope_n, illum, darkness

    tick(94, "Assembling and saving...")
    if frame_seg:
        n_frame = len(frame_seg)
        ax.add_collection(LineCollection(
            frame_seg, linewidths=0.35, colors=[(*ink_rgb, 0.45)], zorder=4))
    if fall_seg:
        fs = np.concatenate(fall_seg)
        n_fall = len(fs)
        ax.add_collection(LineCollection(
            fs, linewidths=np.concatenate(fall_lw),
            colors=np.concatenate(fall_col), capstyle="round", zorder=5))

    # -- decoration over the DOWNSAMPLED disp (full-sheet coordinates) --
    ov = overlays or {}
    if auto_sea:
        _sr = gridmod.sea_polygons(z_ds, g_ds.geff, sea_level)
        if _sr:
            ov = dict(ov); ov["sea_auto"] = list(ov.get("sea_auto", [])) + _sr
    styles = theme.resolve(theme.background_of(fill_mode), paper=bg, ink=ink)
    if ov:
        tick(96, "Decoration (waters/roads/land cover)...")
        compose.set_disp_scale((g_ds.ny / float(R), g_ds.nx / float(C),
                                R / float(g_ds.ny)))
        try:
            _mpp = (abs(grid.geff[1]) + abs(grid.geff[5])) / 2.0
            lcpat = dict(forest=7 * _mpp, sand=5 * _mpp, ice=6 * _mpp,
                         scrub=11 * _mpp, grass=9 * _mpp)
            compose.draw_landcover(ax, ov, grid.geff, disp_ds, styles, lcpat,
                                   z0=4.5, vis=None)
            pat = (dict(enable=True, vignette_step=6 * _mpp, vignette_n=3,
                        hatch_spacing=7 * _mpp, marsh_spacing=14 * _mpp,
                        extent=grid.extent) if water_patterns else None)
            compose.draw_area_waters(ax, ov, grid.geff, disp_ds, styles,
                                     z0=6, pat=pat)
            compose.draw_infrastructure(ax, ov, grid.geff, disp_ds, styles,
                                        vis=None, z0=7)
        finally:
            compose.set_disp_scale(None)

    margin = 0.04 * max(R, C)
    n_sheet = {}
    if sheet:
        from . import sheet as sheetmod
        n_sheet = sheetmod.draw_sheet(
            ax, grid.geff, grid.proj, R, C, margin, bg, ink, sheet,
            top_pad=disp_max_g,
            extras=dict(styles=styles, overlays=overlays,
                        fall=draw_fall, stipple=False, auto_sea=auto_sea),
            log=lambda m: tick(97, m))
    ax.set_xlim(-margin, C + margin)
    ax.set_ylim(R + margin, -disp_max_g - margin)
    ax.set_aspect("equal"); ax.axis("off")
    plt.subplots_adjust(0, 0, 1, 1)
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    plt.savefig(out_png, dpi=dpi, facecolor=fig.get_facecolor(),
                bbox_inches="tight", pad_inches=0.0)
    plt.close(fig)
    if sheet and sheet.get("misreg", 0) > 0:
        from . import print_fx
        print_fx.misregister(out_png, sheet["misreg"],
                             log=lambda m: tick(99, m))
    tick(100, "Done.")
    return dict(rows=R, cols=C, strips=len(starts), fall_segs=n_fall,
                frame_segs=n_frame, max_disp_px=disp_max_g, **n_sheet)

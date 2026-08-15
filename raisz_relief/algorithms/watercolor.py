# -*- coding: utf-8 -*-
"""
watercolor.py -- watercolour styling of the fill: a post-process on RGBA
in plan view.

Runs BETWEEN assembling the fill and draping it (fills.build_base_fill),
that is in plan, before the displacement by disp. This matters: paper grain
and the wet edge belong to the SHEET, but applied after draping they would
land on top of the hachuring and their edges would drift away from the fill
they are meant to outline. So the effects are computed in plan and draped
together with the colour.

The model follows Bousseau et al., NPAR 2006 (stylisation without fluid
simulation) rather than Curtis et al., SIGGRAPH 1997 (shallow-water
simulation). The reason is the task: this is a wash under pen hachuring,
with at most three layers (hypsometry, land cover, water). Across two or
three glazes the spectral accuracy of mixing is invisible, whereas grain,
wet edge and edge wobble are visible at once. Curtis is used narrowly --
his inverse K/S formulas drive the land-cover glaze (see glaze_km).

The key Bousseau formula, through which ALL effects are expressed:

    C' = C * (1 - (1 - C)(d - 1))

where d is pigment density and d=1 leaves the base colour. Above one it
darkens and saturates (edge of a pool, a pit in the paper); below one it
lightens (a ridge of the grain). One knob for everything: edge darkening
raises d along the gradient, grain modulates d with noise, a glaze adds a
layer on top.

All operations run in LINEAR space (sRGB gamma removed and restored),
otherwise the multiplications muddy the midtones.

Dependencies: numpy, scipy.ndimage.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage


# ---------------------------------------------------------------- gamma

def srgb_to_linear(c):
    c = np.clip(np.asarray(c, "float64"), 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, "float64"), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92,
                    1.055 * (c ** (1.0 / 2.4)) - 0.055)


# ---------------------------------------------------------------- noise

def fbm(shape, cell_px, octaves=4, seed=0, gain=0.5):
    """Fractal noise in roughly the 0..1 range.

    Built from white noise by Gaussian smoothing rather than from a
    gradient lattice: Perlin/Simplex would need an external dependency,
    while grain and warp only need a 1/f spectrum, which this produces.

    cell_px is the size of the largest detail in OUTPUT pixels, not metres.
    Tying it to the sheet rather than the terrain is mandatory: paper grain
    does not scale with the map.
    """
    rng = np.random.RandomState(int(seed))
    out = np.zeros(shape, "float64")
    amp, total, s = 1.0, 0.0, float(max(cell_px, 1.0))
    for _ in range(int(max(octaves, 1))):
        n = rng.standard_normal(shape)
        ndimage.gaussian_filter(n, sigma=s / 2.0, output=n)
        sd = n.std()
        if sd > 1e-9:
            out += amp * (n / sd)
        total += amp
        amp *= float(gain)
        s = max(s / 2.0, 0.7)
        if s <= 0.75:
            break
    out /= max(total, 1e-9)
    return np.clip(0.5 + 0.25 * out, 0.0, 1.0)


# ------------------------------------------------------- pigment density

def apply_density(rgb_lin, d):
    """Bousseau equation (1): C' = C*(1 - (1 - C)(d - 1)).

    Works per channel, so saturation rises together with density: the dark
    channel darkens more than the light one. That is exactly what separates
    density modulation from a plain multiply by brightness, which greys."""
    d = np.asarray(d, "float64")[..., None] if np.ndim(d) == 2 else d
    return np.clip(rgb_lin * (1.0 - (1.0 - rgb_lin) * (d - 1.0)), 0.0, 1.0)


# ------------------------------------------------------------ Kubelka-Munk

def km_from_swatches(rgb_white, rgb_black, eps=1e-6):
    """Inverse Kubelka-Munk problem (Curtis et al. 1997, sect. 5.1): K and S
    of a pigment from how a unit layer looks ON WHITE and ON BLACK.

    No spectral measurements are needed -- both colours are chosen by
    design, which is what a cartographic palette calls for. Returns (K, S)
    per RGB channel."""
    Rw = np.clip(np.asarray(rgb_white, "float64"), eps, 1.0 - eps)
    Rb = np.clip(np.asarray(rgb_black, "float64"), eps, 1.0 - eps)
    Rb = np.minimum(Rb, Rw - eps)
    a = 0.5 * (Rw + (Rb - Rw + 1.0) / np.maximum(Rb, eps))
    b = np.sqrt(np.maximum(a * a - 1.0, eps))
    arg = np.clip((b * b - (a - Rw) * (a - 1.0)) / np.maximum(b * (1.0 - Rw),
                                                             eps),
                  1.0 + eps, None)
    S = np.arctanh(np.clip(1.0 / arg, -1.0 + eps, 1.0 - eps)) / b
    S = np.abs(S)
    return S * (a - 1.0), S


def glaze_km(base_lin, rgb_white, rgb_black, thickness):
    """Lay a glaze over a substrate by Kubelka-Munk.

    R = sinh(b*S*x)/c,  T = b/c,  c = a*sinh(b*S*x) + b*cosh(b*S*x)
    and layer compositing (Curtis, sect. 5.2):
        R_total = R + T^2*Rb / (1 - R*Rb)

    This is NOT an alpha composite: a thin layer passes light down to the
    substrate and back, so forest over ochre and forest over green give
    different hues, whereas alpha blending would give the same colour with
    a different admixture. thickness is a map (0 = no layer) and doubles as
    the "density" knob."""
    K, S = km_from_swatches(rgb_white, rgb_black)
    x = np.asarray(thickness, "float64")[..., None]
    KS = K / np.maximum(S, 1e-9)
    a = 1.0 + KS
    b = np.sqrt(np.maximum(a * a - 1.0, 1e-12))
    bSx = np.clip(b * S * x, 0.0, 30.0)          # sinh overflows beyond this
    sh, ch = np.sinh(bSx), np.cosh(bSx)
    c = a * sh + b * ch
    R = sh / np.maximum(c, 1e-12)
    T = b / np.maximum(c, 1e-12)
    Rb = np.clip(base_lin, 0.0, 1.0)
    return np.clip(R + (T * T * Rb) / np.maximum(1.0 - R * Rb, 1e-6), 0.0, 1.0)


# ------------------------------------------------------------------ effects

def edge_darkening(rgb_lin, alpha, width_px=2.0, strength=0.5):
    """The wet edge: pigment is carried to the rim of a drying pool and
    settles as a dark rim. Implemented as a rise in density along the
    gradient.

    The gradient is taken from LUMINANCE times alpha: the edge is wanted
    both where the colour changes (a hypsometric step boundary) and where
    the fill ends (a shore, the rim of a forest)."""
    if strength <= 0:
        return rgb_lin
    lum = (0.2126 * rgb_lin[..., 0] + 0.7152 * rgb_lin[..., 1]
           + 0.0722 * rgb_lin[..., 2]) * np.clip(alpha, 0.0, 1.0)
    g = (np.abs(np.roll(lum, 1, 0) - np.roll(lum, -1, 0))
         + np.abs(np.roll(lum, 1, 1) - np.roll(lum, -1, 1)))
    if width_px > 0:
        g = ndimage.gaussian_filter(g, sigma=float(width_px))
    p95 = np.percentile(g[g > 0], 95) if np.any(g > 0) else 1.0
    g = np.clip(g / max(p95, 1e-9), 0.0, 1.0)
    return apply_density(rgb_lin, 1.0 + strength * g)


def granulate(rgb_lin, grain_px=3.0, strength=0.25, seed=7):
    """Granulation: pigment settles in the pits of the paper, so density
    varies pixel to pixel. White noise would read as digital, hence the 1/f
    spectrum."""
    if strength <= 0:
        return rgb_lin
    n = fbm(rgb_lin.shape[:2], grain_px, octaves=3, seed=seed)
    return apply_density(rgb_lin, 1.0 + strength * (2.0 * n - 1.0))


def wobble(field, amp_px=1.5, cell_px=24.0, seed=11):
    """Edge wobble: a real rim does not follow the geometric line, the paper
    grain steers it. The displacement along each axis comes from two
    independent noise fields -- Bousseau takes it from the gradient of the
    paper texture; this is simpler and the result is the same.

    Applied to the MAP (to indices), so it serves both RGBA and a mask."""
    if amp_px <= 0:
        return field
    h, w = field.shape[:2]
    dy = (fbm((h, w), cell_px, octaves=2, seed=seed) - 0.5) * 2.0 * amp_px
    dx = (fbm((h, w), cell_px, octaves=2, seed=seed + 1) - 0.5) * 2.0 * amp_px
    rr, cc = np.mgrid[0:h, 0:w].astype("float64")
    coords = np.stack([np.clip(rr + dy, 0, h - 1), np.clip(cc + dx, 0, w - 1)])
    if field.ndim == 2:
        return ndimage.map_coordinates(field, coords, order=1, mode="nearest")
    out = np.empty_like(field)
    for k in range(field.shape[2]):
        out[..., k] = ndimage.map_coordinates(field[..., k], coords,
                                              order=1, mode="nearest")
    return out


def warp_field(z, amp_px=6.0, cell_px=40.0, seed=3):
    """Domain warping: perturb the field BEFORE quantising it into steps, so
    the step boundaries do not follow the DEM contours literally.

    It is the elevation that is perturbed, not the finished boundary:
    shifting a contour would look like a uniform offset, whereas warping the
    elevation gives an irregularity that travels with the terrain. The same
    noise must be applied to the land-cover masks too, otherwise the forest
    ends up pasted onto the steps."""
    if amp_px <= 0:
        return z
    return wobble(z, amp_px=amp_px, cell_px=cell_px, seed=seed)


def paper_texture(shape, cell_px=2.5, strength=0.35, seed=21):
    """Paper tone: a brightness multiplier around one. Kept apart from
    pigment grain, because the paper shows through where there is no
    colour at all."""
    if strength <= 0:
        return np.ones(shape, "float64")
    n = fbm(shape, cell_px, octaves=3, seed=seed)
    return np.clip(1.0 - strength * 0.12 * (2.0 * n - 1.0), 0.0, 1.5)


# -------------------------------------------------------------- pipeline

def watercolorize(rgba, *, strength=1.0, edge=1.1, grain=0.6, wobble_px=2.0,
                  paper=0.55, grain_px=3.5, seed=17, masks=None,
                  glazes=None, log=None):
    """Watercolourise a finished RGBA fill (in plan, before draping).

    masks is a dict name -> mask 0..1 (forest, marsh, water); glazes is
    {name: (colour_on_white, colour_on_black, thickness)}. Glazes go through
    Kubelka-Munk rather than an alpha composite, so the substrate shows
    through and forest reads differently over different steps.

    Defaults are three times the first edition. There they came from the
    manifest (+-3-5% brightness), but that is a figure for PURE watercolour,
    whereas this is a wash under dense hachuring, plains stippling and bulk
    shading: on a real render the effect came to 4 levels out of 255 and was
    simply invisible. Grain now gives about +-22 levels and the wet edge at
    a step boundary about 33.

    Order exactly as in the manifest: steps -> land-cover glazes -> wet edge
    AFTER compositing (otherwise the edge would follow the boundaries rather
    than the finished image) -> water with its own edge -> grain and paper
    over the WHOLE sheet, water included (otherwise lakes look like
    stickers).
    """
    if rgba is None or strength <= 0:
        return rgba
    s = float(np.clip(strength, 0.0, 1.0))
    out = np.array(rgba, dtype="float64", copy=True)
    alpha = out[..., 3].copy()
    lin = srgb_to_linear(out[..., :3])

    for name, (c_white, c_black, thick) in (glazes or {}).items():
        m = (masks or {}).get(name)
        if m is None:
            continue
        m = np.clip(np.asarray(m, "float64"), 0.0, 1.0)
        if wobble_px > 0:
            # the same wobble as the fill: otherwise the rim of a forest
            # would run geometrically straight beside a wobbling step edge
            m = wobble(m, amp_px=wobble_px * s, cell_px=24.0,
                       seed=seed + abs(hash(name)) % 97)
        if not np.any(m > 0.01):
            continue
        g = glaze_km(lin, c_white, c_black, m * float(thick) * s)
        lin = lin * (1.0 - m[..., None]) + g * m[..., None]
        alpha = np.maximum(alpha, m * np.max(np.clip(alpha, 0.05, 1.0)))
        if log:
            log("Watercolour: glaze '%s' over %.1f%% of the area"
                % (name, 100.0 * float((m > 0.5).mean())))

    lin = edge_darkening(lin, alpha, width_px=2.0, strength=edge * s)
    lin = granulate(lin, grain_px=grain_px, strength=grain * s, seed=seed)
    lin *= paper_texture(lin.shape[:2], strength=paper * s,
                         seed=seed + 5)[..., None]

    out[..., :3] = linear_to_srgb(np.clip(lin, 0.0, 1.0))
    out[..., 3] = np.clip(alpha, 0.0, 1.0)
    return out


# ---------------------------------------------------------------- palette

# Pigments are given as a pair: how a unit layer looks on white paper and
# the same layer over a black substrate. The inverse Curtis problem
# (sect. 5.1) derives K and S from them -- no measurements needed, the
# colours are chosen by design.
#
# The pair, rather than a single colour, is the substance of the model: the
# difference between the two sets the HIDING POWER. Forest is noticeably
# lighter than zero on black -- the layer scatters and partly covers; marsh
# is almost black -- the glaze is transparent; the sea has the most opaque
# pair, so water reads as a layer rather than a film.
#
# The third number is thickness -- the "density" knob; 0 disables the layer.
WC_GLAZES = {
    "forest": ((0.44, 0.54, 0.34), (0.10, 0.15, 0.08), 0.55),
    "scrub":  ((0.58, 0.62, 0.42), (0.13, 0.16, 0.10), 0.35),
    "grass":  ((0.72, 0.74, 0.50), (0.17, 0.19, 0.12), 0.28),
    "marsh":  ((0.58, 0.66, 0.60), (0.09, 0.13, 0.12), 0.30),
    "sand":   ((0.88, 0.82, 0.62), (0.24, 0.22, 0.15), 0.25),
    "ice":    ((0.90, 0.93, 0.96), (0.30, 0.34, 0.38), 0.22),
    "lake":   ((0.52, 0.65, 0.72), (0.12, 0.19, 0.24), 0.60),
    "sea":    ((0.48, 0.62, 0.71), (0.14, 0.22, 0.28), 0.75),
}

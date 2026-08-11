#!/usr/bin/env python3
"""
Rebuild all 191 colour swatches from 16 photographed base plates.

The point of this pass is that the weave survives the recolour. Previous
attempts tinted in RGB, which squeezes every fibre into whatever narrow slice
of the range the target colour occupies -- 76 of the 191 colours sit below
L*20, so the texture had nowhere left to live.

Three things keep the detail here:

  * Recolour additively in CIE L*a*b*. L* is perceptually uniform, so shifting
    the whole plate by a constant moves the colour without changing how strong
    the weave contrast *looks*.
  * Pick the nearer of the two base plates (light or dark) per colour, so the
    shift is short and the soft-knee barely has to work.
  * Compress the tails exponentially instead of clipping. exp() is strictly
    monotonic, so the deepest shadow still carries gradient -- squashed, but
    never a flat black slab.

Every collection is cropped at the same scale, and the tiles are written at 2x
so a fine weave survives being resampled down. See ZOOM below for why the scale
has to be shared even though it costs resolution to hold it there.
"""

import json
import os
import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SW = os.path.join(ROOT, "assets", "swatches")

# Which base plate family each collection draws from, and whether it was shot
# flat (firm fabrics -- the weave is the signal) or draped (soft fabrics --
# the fold is the signal). Set in the audit; see manifest for donor names.
FORMAT = {
    "luna": "flat", "spello": "flat", "enjoylux": "flat", "milton": "flat",
    "manila": "drape", "piano": "drape", "maya": "drape", "zoya": "drape",
}

# One zoom for every collection, deliberately.
#
# Per-collection zoom was tried and it lies. All 16 plates were shot at the
# same physical scale, so magnifying one fabric and not another inverts the
# relationship the customer is actually judging -- a zoomed velvet reads
# coarser than a shrunk texturat, when in the hand it is the smoother cloth.
# Whatever the crop is, it has to be the same crop everywhere, so that a
# swatch looking rougher than its neighbour means it *is* rougher.
#
# Holding zoom at 1.0 brings back the aliasing that zoom was papering over: a
# fine weave resampled from 1120px to a 320px tile turns to porridge. That is
# a resolution problem, so it gets a resolution fix -- the tiles below are 2x
# and the browser scales them down -- rather than a zoom fix that would cost
# the honesty of the comparison.
ZOOM = 1.0

HERO_SIZE = (1024, 576)
THUMB_SIZE = (640, 360)   # 2x the 320x180 the grid displays at
DROP_SIZE = (320, 320)    # 2x the 160x160 drop-in overlay

FLOOR, CEIL = 1.0, 99.0     # L* limits the soft-knee asymptotes toward
CHROMA_KEEP = 0.45          # how much of the plate's own hue drift to retain

# ---------------------------------------------------------------- colour math

_M_RGB2XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                       [0.2126729, 0.7151522, 0.0721750],
                       [0.0193339, 0.1191920, 0.9503041]], dtype=np.float32)
_M_XYZ2RGB = np.linalg.inv(_M_RGB2XYZ).astype(np.float32)
_WP = np.array([0.95047, 1.00000, 1.08883], dtype=np.float32)


def _srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def _f(t):
    d = 6 / 29
    return np.where(t > d ** 3, np.cbrt(t), t / (3 * d * d) + 4 / 29)


def _finv(t):
    d = 6 / 29
    return np.where(t > d, t ** 3, 3 * d * d * (t - 4 / 29))


def rgb_to_lab(rgb):
    """rgb float32 in [0,1], shape (...,3) -> L*a*b*"""
    xyz = _srgb_to_linear(rgb) @ _M_RGB2XYZ.T / _WP
    fx, fy, fz = _f(xyz[..., 0]), _f(xyz[..., 1]), _f(xyz[..., 2])
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], axis=-1)


def lab_to_rgb(lab):
    """L*a*b* -> rgb float32, may fall outside [0,1] when out of gamut"""
    fy = (lab[..., 0] + 16) / 116
    fx = fy + lab[..., 1] / 500
    fz = fy - lab[..., 2] / 200
    xyz = np.stack([_finv(fx), _finv(fy), _finv(fz)], axis=-1) * _WP
    return _linear_to_srgb(xyz @ _M_XYZ2RGB.T)


def hex_to_lab(h):
    v = np.array([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)], dtype=np.float32)
    return rgb_to_lab(v)


# ---------------------------------------------------------------- the recolour

def soft_knee(residual, down, up):
    """Additive L* offset with exponential tails.

    Slope is exactly 1 at residual 0, so mid-tones keep their full contrast.
    Approaching either limit the response flattens but never reaches it, which
    is what stops the shadows collapsing into a single value.
    """
    down = max(down, 0.5)
    up = max(up, 0.5)
    return np.where(
        residual < 0,
        -down * (1.0 - np.exp(residual / down)),
        up * (1.0 - np.exp(-residual / up)),
    )


def fit_gamut(lab, iters=6):
    """Pull chroma in until the colour fits sRGB, leaving L* alone.

    Clipping RGB per channel would shift hue and flatten saturated darks, so
    scale a/b instead and keep the lightness structure the weave lives in.
    """
    lo = np.zeros(lab.shape[:-1], dtype=np.float32)
    hi = np.ones(lab.shape[:-1], dtype=np.float32)
    ok = np.ones(lab.shape[:-1], dtype=bool)
    test = lab.copy()
    for _ in range(iters):
        mid = (lo + hi) / 2
        test[..., 1] = lab[..., 1] * mid
        test[..., 2] = lab[..., 2] * mid
        rgb = lab_to_rgb(test)
        ok = (rgb >= -1e-4).all(-1) & (rgb <= 1 + 1e-4).all(-1)
        lo = np.where(ok, mid, lo)
        hi = np.where(ok, hi, mid)
    out = lab.copy()
    out[..., 1] = lab[..., 1] * lo
    out[..., 2] = lab[..., 2] * lo
    return out


def recolour(base_lab, base_mean, target_lab):
    tL, ta, tb = float(target_lab[0]), float(target_lab[1]), float(target_lab[2])

    resid = base_lab[..., 0] - base_mean[0]
    out_L = tL + soft_knee(resid, tL - FLOOR, CEIL - tL)

    # Hue wander read off the plate is partly real fibre colour and partly the
    # source JPEG's chroma noise. On a light target that noise is invisible; on
    # a near-black one it surfaces as magenta speckle, because a/b are absolute
    # and don't shrink as L* does. So fade the borrowed chroma out in the darks.
    keep = CHROMA_KEEP * float(np.clip(tL / 35.0, 0.22, 1.0))

    # Highlights desaturate the way real pile does when it catches light.
    sheen = np.clip(1.0 - np.maximum(resid, 0) / 45.0, 0.55, 1.0)
    out_a = ta * sheen + (base_lab[..., 1] - base_mean[1]) * keep
    out_b = tb * sheen + (base_lab[..., 2] - base_mean[2]) * keep

    lab = np.stack([out_L, out_a, out_b], axis=-1).astype(np.float32)
    return np.clip(lab_to_rgb(fit_gamut(lab)), 0, 1)


# ---------------------------------------------------------------- output sizes

def crop_box(size, frac, aspect):
    w, h = size
    cw = w * frac
    ch = cw / aspect
    if ch > h * frac:
        ch = h * frac
        cw = ch * aspect
    return cw, ch


def best_crop_offset(plate_lab, frac, aspect, steps=9):
    """Find the window of the plate carrying the most structure.

    A centred crop is the obvious choice and it loses the shot on drapes: the
    fold in a velvet plate is wherever the photographer put it, often near an
    edge, and the middle of a near-black velvet is an empty black field. So
    score candidate windows on the base plate's own gradient energy and keep
    the busiest one. The structure sits in the same place after recolouring,
    so this only needs computing once per plate.
    """
    h, w = plate_lab.shape[:2]
    cw, ch = crop_box((w, h), frac, aspect)
    L = plate_lab[..., 0]
    gy, gx = np.gradient(L)
    energy = np.hypot(gx, gy)
    best, bx, by = -1.0, (w - cw) / 2, (h - ch) / 2
    for iy in range(steps):
        for ix in range(steps):
            x = (w - cw) * ix / max(steps - 1, 1)
            y = (h - ch) * iy / max(steps - 1, 1)
            win = energy[int(y):int(y + ch), int(x):int(x + cw)]
            s = float(win.mean())
            if s > best:
                best, bx, by = s, x, y
    return int(bx), int(by), int(cw), int(ch)


def crop_at(img, box):
    x, y, cw, ch = box
    return img.crop((x, y, x + cw, y + ch))


def detail_energy(img):
    """Mean gradient magnitude -- a proxy for how much weave survived."""
    a = np.asarray(img.convert("L"), dtype=np.float32)
    gy, gx = np.gradient(a)
    return float(np.hypot(gx, gy).mean())


def main():
    manifest = json.load(open(os.path.join(SW, "manifest.json")))
    os.makedirs(os.path.join(SW, "thumb"), exist_ok=True)
    os.makedirs(os.path.join(SW, "dropin"), exist_ok=True)

    plates = {}
    for coll in manifest:
        for tone in ("light", "dark"):
            im = Image.open(os.path.join(SW, f"{coll}-{tone}.jpg")).convert("RGB")
            arr = np.asarray(im, dtype=np.float32) / 255.0
            lab = rgb_to_lab(arr)
            probe = rgb_to_lab(
                np.asarray(im.resize((300, 300), Image.LANCZOS), dtype=np.float32) / 255)
            plates[(coll, tone)] = (lab, lab.reshape(-1, 3).mean(0),
                                    detail_energy(im), probe)

    boxes = {}
    for coll in manifest:
        for tone in ("light", "dark"):
            lab = plates[(coll, tone)][0]
            boxes[(coll, tone, "hero")] = best_crop_offset(lab, ZOOM, 16 / 9)
            boxes[(coll, tone, "thumb")] = best_crop_offset(lab, ZOOM, 16 / 9)
            boxes[(coll, tone, "drop")] = best_crop_offset(lab, ZOOM, 1.0)

    report = []
    for coll, data in manifest.items():
        drape = FORMAT[coll] == "drape"
        for c in data["colors"]:
            target = hex_to_lab(c["hex"])

            # Shortest journey wins: whichever plate already sits nearer this
            # lightness needs the least compression to get there.
            #
            # Picking instead by "which base yields the most measured grain"
            # was tried and is wrong. The dark plates in this set are simply
            # the contrastier photographs, so that rule selects them for every
            # colour including the near-whites, and a pale fabric rendered off
            # a near-black plate comes out blotchy rather than detailed. Raw
            # gradient measures contrast, not plausibility.
            def dist(t):
                return abs(plates[(coll, t)][1][0] - float(target[0]))

            # An "escape to the other plate when this one looks flat" rule was
            # tried here too. It fired on every Enjoy Lux and Spello colour --
            # their light plates are smooth *because the fabric is smooth*, not
            # because the exposure failed -- and never fired for Piano, the one
            # case it existed for. Low measured grain doesn't distinguish a bad
            # photo from a genuinely soft cloth, so there is no rule here.
            tone = min(("light", "dark"), key=dist)
            lab, mean, base_energy, _ = plates[(coll, tone)]

            rgb = recolour(lab, mean, target)
            full = Image.fromarray((rgb * 255 + 0.5).astype(np.uint8), "RGB")

            # 4:4:4 subsampling throughout -- 4:2:0 averages chroma over 2x2
            # blocks, which is exactly the scale the weave lives at.
            hero = crop_at(full, boxes[(coll, tone, "hero")]).resize(
                HERO_SIZE, Image.LANCZOS)
            hero.save(os.path.join(SW, c["file"]), quality=94, subsampling=0)

            # Drapes read by their fold, so keep the frame. Flats zoom by however
            # much their weave needs to clear the resampling floor -- no more.
            thumb = crop_at(full, boxes[(coll, tone, "thumb")]).resize(
                THUMB_SIZE, Image.LANCZOS)
            thumb.save(os.path.join(SW, "thumb", c["file"]), quality=94, subsampling=0)

            drop = crop_at(full, boxes[(coll, tone, "drop")]).resize(
                DROP_SIZE, Image.LANCZOS)
            drop.save(os.path.join(SW, "dropin", c["dropin"]))

            report.append((coll, c["code"], c["hex"], tone, float(target[0]),
                           base_energy, detail_energy(hero)))

    print(f"{'coll':10} {'n':>3}  {'light/dark':10}  {'detail kept vs plate':>20}")
    for coll in manifest:
        rows = [r for r in report if r[0] == coll]
        nl = sum(1 for r in rows if r[3] == "light")
        keep = [r[6] / r[5] for r in rows if r[5] > 0]
        worst = min(keep)
        print(f"{coll:10} {len(rows):3}  {nl:2}/{len(rows)-nl:<7}  "
              f"mean {np.mean(keep):5.2f}x   worst {worst:5.2f}x")

    allkeep = [r[6] / r[5] for r in report if r[5] > 0]
    print(f"\n{len(report)} swatches. detail retention "
          f"min {min(allkeep):.2f}x  median {np.median(allkeep):.2f}x")
    low = sorted([r for r in report if r[6] / r[5] < 0.6], key=lambda r: r[6] / r[5])
    if low:
        print(f"\n{len(low)} below 0.60x:")
        for r in low[:12]:
            print(f"  {r[0]}-{r[1]} {r[2]} L*={r[4]:5.1f} via {r[3]:5}  {r[6]/r[5]:.2f}x")


if __name__ == "__main__":
    main()

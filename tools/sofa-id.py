#!/usr/bin/env python3
"""
Build sofa renders for all 191 colours from Interior Define's Sloan set.

Same L*a*b* recolour as the swatches and the same two-plate trick: a light and
a dark source per collection, chosen so every colour has a short journey.

Masking is the interesting part. The obvious approach -- threshold on chroma,
as the Natalie cutout does -- fails outright here, because three of the source
renders are upholstered in a perfectly neutral fabric (chroma 0.0) and so are
indistinguishable from their own legs and shadow.

What rescues it is that this is a CGI set: the sofa lands on the same pixels in
almost every frame. So the fabric/not-fabric split is solved *once*, on the most
saturated render in the set, where the separation is unambiguous -- and then
reused everywhere, including on the neutral ones.

"Almost every frame" is doing real work in that sentence. Most renders agree to
IoU 0.9999, but a couple sit ~10px off, so the master mask is translated onto
each image by its own measured silhouette offset rather than pasted blind.
"""

import json
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "swatch", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "regen-swatches.py"))
swatch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(swatch)

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = "/Users/eduard/Downloads/ID Sofas"
SIZE = 1120

# The render whose fabric is most saturated -- Chartreuse, chroma median 52 --
# so fabric separates from the neutral legs and shadow without ambiguity.
MASTER = "se__CroppedRomanceImages_SLON.FABRIC.SOFA.3SEAT.Chartreuse.jpg"
MASTER_CHROMA = 6.0

# One family per collection, so no two collections share a render. Six match the
# swatch donor exactly. Enjoy Lux and Milton don't: their swatches were moved to
# velvet plates to fix a smoothness inversion, but that fix relied on shooting
# velvet *flat*, and a sofa has no flat/draped variant. Rather than have two
# pairs of collections come back as the same photograph, these two revert to the
# woven families they held before that change.
SOURCES = {
    "luna":     ("gia__1624416315_alabaster.jpg",
                 "gia__1611859565_perf-linen-weave-currant.jpg"),
    "spello":   ("cu__1611873720_heathered-weave-chalk-2.jpg",
                 "cu__1611873849_heathered-weave-azure-2.jpg"),
    "manila":   ("cov__1627395030_blanc.jpg",
                 "cov__1611859623_perf-vintage-velvet-mocha.jpg"),
    "piano":    ("se__1638313326_sterling.jpg",
                 "se__1611873921_perf-velvet-peacock.jpg"),
    "maya":     ("plush__1611874105_vintage-plush-sisal_-2.jpg",
                 "plush__Bayou-Sloan-Rendering.jpg"),
    "zoya":     ("mono__1611872879_mono-plush-ecru.jpg",
                 "mono__1611872931_mono-plush-union.jpg"),
    "enjoylux": ("cas__1635270486_classic-bisque.jpg",
                 "cas__1635273035_classic-cove.jpg"),
    "milton":   ("am__1635276308_loop-champagne.jpg",
                 "am__1635276913_loop-thunder.jpg"),
}

CARD_BG = (244, 243, 241)

# Breathing room around the sofa, as fractions of the finished square. Sized so
# the piece sits inside the frame rather than filling it -- a tile cropped tight
# to the upholstery reads as a fabric close-up, not as furniture. Slightly more
# air below than above so the sofa sits marginally high, which stops it looking
# like it is sliding off the bottom of the card.
AIR_TOP, AIR_BOTTOM, AIR_LEFT = 0.11, 0.17, 0.09


def load(name):
    im = Image.open(os.path.join(SRC, name)).convert("RGB")
    if im.size != (SIZE, SIZE):
        im = im.resize((SIZE, SIZE), Image.LANCZOS)
    return np.asarray(im, dtype=np.float32) / 255.0


def silhouette(arr, tol=0.03):
    """Sofa + legs + shadow against the flat backdrop.

    Works on every render regardless of fabric chroma, which is why offsets can
    be measured even where the fabric/leg split can't be.

    The tolerance has to be this low. At 0.10 a pale fabric on a pale backdrop
    loses huge parts of itself -- Blanc detects 409k pixels against a true 750k
    -- and every measurement downstream inherits the error. The backdrops are
    perfectly flat, so there is no noise floor forcing a high threshold.
    """
    return fill_interior(np.abs(arr - arr[5, 5]).max(-1) > tol)


def align(master_sil, img_sil):
    """Translation that best lands the master silhouette on this render's.

    Taking the offset from each silhouette's top-left corner is tempting and
    too brittle: one stray antialiased pixel moves the corner and drags the
    whole mask with it. Overlap is a consensus of ~750k pixels, so a bad edge
    costs nothing. Coarse pass on a downsample, then refine at full scale.
    """
    def iou(a, b):
        return (a & b).sum() / max((a | b).sum(), 1)

    small_m = master_sil[::4, ::4]
    small_i = img_sil[::4, ::4]
    best, bdx, bdy = -1.0, 0, 0
    for dy in range(-6, 7):
        for dx in range(-6, 7):
            s = iou(shift(small_m, dx, dy), small_i)
            if s > best:
                best, bdx, bdy = s, dx, dy
    bdx, bdy = bdx * 4, bdy * 4
    for dy in range(bdy - 3, bdy + 4):
        for dx in range(bdx - 3, bdx + 4):
            s = iou(shift(master_sil, dx, dy), img_sil)
            if s > best:
                best, bdx, bdy = s, dx, dy
    return bdx, bdy, best


def shift(mask, dx, dy):
    out = np.zeros_like(mask)
    h, w = mask.shape
    sy0, sy1 = max(0, -dy), min(h, h - dy)
    sx0, sx1 = max(0, -dx), min(w, w - dx)
    out[sy0 + dy:sy1 + dy, sx0 + dx:sx1 + dx] = mask[sy0:sy1, sx0:sx1]
    return out


def fill_interior(mask):
    """Fill anything enclosed by the silhouette.

    A sofa is solid: any 'background' pixel that can't be reached from the
    frame edge is really fabric that happened to match the backdrop. That
    happens a lot on the pale colourways -- a highlight on Chalk sits within
    the tolerance of its own light-grey sweep -- and each such pixel would
    otherwise survive the recolour as a bright speck of the source colour.
    """
    im = Image.fromarray(np.where(mask, 0, 255).astype(np.uint8))
    ImageDraw.floodfill(im, (0, 0), 128)
    reached = np.asarray(im, dtype=np.uint8)
    return mask | (reached == 255)


def close_holes(mask, radius=7):
    """Morphological close -- dilate then erode -- to plug speckle holes.

    Where light catches the pile the fabric's chroma washes out below the
    threshold, so the raw mask is peppered with tiny holes exactly on the
    highlights. Left alone they survive the recolour as bright specks of the
    source colour, most visibly on the pale collections. Legs and shadow are
    far larger than the kernel, so closing doesn't swallow them.
    """
    im = Image.fromarray((mask * 255).astype(np.uint8))
    im = im.filter(ImageFilter.MaxFilter(radius)).filter(ImageFilter.MinFilter(radius))
    return np.asarray(im, dtype=np.uint8) > 127


def build_master():
    arr = load(MASTER)
    lab = swatch.rgb_to_lab(arr)
    sil = silhouette(arr)
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    fabric = close_holes(sil & (chroma > MASTER_CHROMA))
    return fabric & sil, sil


def fabric_mask(arr, master, master_sil, feather=1.0):
    img_sil = silhouette(arr)
    dx, dy, score = align(master_sil, img_sil)
    # Never paint outside this render's own silhouette, whatever the alignment
    # says. Bounds the damage if a future render doesn't match the set.
    m = (shift(master, dx, dy) & img_sil).astype(np.float32)
    if feather:
        m = np.asarray(Image.fromarray((m * 255).astype(np.uint8))
                       .filter(ImageFilter.GaussianBlur(feather)),
                       dtype=np.float32) / 255.0
        m = m * img_sil
    return m, (dx, dy, score)


def crop_left_square(img_arr, mask):
    """Square framing showing the left of the sofa, with air around it.

    The square is derived from the sofa's height plus the air above and below
    it, so the piece occupies a fixed share of the tile no matter how the
    silhouette is measured. It still runs off the right edge, as the reference
    cards do -- the air is on the other three sides.
    """
    ys, xs = np.where(mask > 0.5)
    x0, y0, y1 = xs.min(), ys.min(), ys.max()
    side = int((y1 - y0) / (1 - AIR_TOP - AIR_BOTTOM))
    left = int(x0 - side * AIR_LEFT)
    top = int(y0 - side * AIR_TOP)
    return left, top, side


def main():
    manifest = json.load(open(os.path.join(ROOT, "assets", "swatches",
                                           "manifest.json")))
    outdir = os.path.join(ROOT, "assets", "sofa")
    os.makedirs(outdir, exist_ok=True)
    master, master_sil = build_master()
    print(f"master mask: {master.sum():,} fabric px")

    total = 0
    for coll, (light_f, dark_f) in SOURCES.items():
        plates = {}
        for tone, fn in (("light", light_f), ("dark", dark_f)):
            arr = load(fn)
            lab = swatch.rgb_to_lab(arr)
            m, (dx, dy, score) = fabric_mask(arr, master, master_sil)
            w = m.reshape(-1)
            mean = (lab.reshape(-1, 3) * w[:, None]).sum(0) / max(w.sum(), 1e-6)
            plates[tone] = (arr, lab, m, mean)
            print(f"  {coll:9} {tone:5} L*={mean[0]:5.1f}  "
                  f"align dx={dx:+3d} dy={dy:+3d} iou={score:.4f}  {fn[:40]}")

        box = crop_left_square(plates["light"][0], plates["light"][2])
        left, top, side = box

        for c in manifest[coll]["colors"]:
            target = swatch.hex_to_lab(c["hex"])
            tone = min(("light", "dark"),
                       key=lambda t: abs(plates[t][3][0] - float(target[0])))
            arr, lab, m, mean = plates[tone]

            out = swatch.recolour(lab, mean, target)
            comp = arr * (1 - m[..., None]) + out * m[..., None]

            # Flatten onto one card colour. The set ships with three different
            # backdrop greys, which read as a rendering bug once tiled.
            bg = ~silhouette(arr)
            card = np.array(CARD_BG, dtype=np.float32) / 255.0
            comp = np.where(bg[..., None], card, comp)

            im = Image.fromarray((np.clip(comp, 0, 1) * 255 + 0.5).astype(np.uint8))
            im.crop((left, top, left + side, top + side)) \
              .resize((900, 900), Image.LANCZOS) \
              .save(os.path.join(outdir, f"{coll}-{c['code']}.jpg"),
                    quality=92, subsampling=0)
            total += 1
    print(f"\nwrote {total} sofas to assets/sofa/")


if __name__ == "__main__":
    main()

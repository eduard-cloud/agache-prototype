#!/usr/bin/env python3
"""
Recolour a sofa render into every colour of a collection.

Same L*a*b* transfer as the swatch rebuild (see regen-swatches.py), pointed at
a product shot instead of a fabric plate. The material is whatever the source
render was upholstered in, so a source shot is needed per collection -- there
is no texture transplant here and no attempt at one.

The difference from a swatch plate is that a plate is 100% fabric and this
isn't. Legs, background and the floor shadow must not move when the colour
does, so everything runs through a soft alpha mask.

Masking is by chroma, not lightness. In these renders the sweep background and
the contact shadow are colourimetrically neutral (C ~ 0.0) while the upholstery
carries chroma even when it reads as near-white beige (C ~ 3.6-7.0). Thresholding
on lightness instead would eat the shadow and the highlight rolloff on the arms.
The mask is soft across the boundary so antialiased edge pixels blend rather
than fringe.
"""

import argparse
import json
import os
import numpy as np
from PIL import Image, ImageFilter

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "swatch", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "regen-swatches.py"))
swatch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(swatch)

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# Two chroma ramps, because the two source types need different jobs done.
#
# On a flat render over a sweep background, chroma has to find the sofa itself:
# background and contact shadow are neutral, upholstery is not, so the ramp
# sits high enough to reject the backdrop.
#
# On a cutout with an alpha channel, alpha already found the sofa. Chroma is
# then only there to reject the *legs*, which are a perfectly neutral grey
# (C = 0.0) against fabric that still carries C ~ 2-5 even in deep shade. Reusing
# the high ramp there would clip the darkest creases out of the mask and leave
# them the source colour -- so the cutout ramp sits far lower.
CHROMA_RAMP_FLAT = (1.6, 3.6)
CHROMA_RAMP_CUTOUT = (0.4, 1.4)


def upholstery_mask(lab, ramp, base_alpha=None, feather=1.2):
    """Soft alpha over the fabric only -- 0 on background, shadow and legs."""
    lo, hi = ramp
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    a = np.clip((chroma - lo) / (hi - lo), 0.0, 1.0)
    a = a * a * (3 - 2 * a)                       # smoothstep
    if feather:
        a = np.asarray(Image.fromarray((a * 255).astype(np.uint8))
                       .filter(ImageFilter.GaussianBlur(feather)),
                       dtype=np.float32) / 255.0
    if base_alpha is not None:
        # Never recolour anything the render itself calls transparent. The
        # contact shadow lives in the alpha channel at ~0.2, so gating on alpha
        # keeps the shadow out of the recolour while leaving it in the output.
        a = a * (base_alpha > 0.99)
    return a


def content_bounds(im, cutout):
    """Bounding box of the sofa, and separately of the sofa plus its shadow."""
    a = np.asarray(im, dtype=np.float32) / 255.0
    if cutout:
        solid, any_ink = a[..., 3] > 0.99, a[..., 3] > 0.01
    else:
        lum = a[..., :3].mean(-1)
        solid = any_ink = lum < 0.96
    ys, xs = np.where(solid)
    ay, ax = np.where(any_ink)
    return (xs.min(), ys.min(), xs.max(), ys.max()), (ay.min(), ay.max())


def crop_left_square(im, cutout, margin):
    """Square framing that shows the left of the sofa and cuts it at the right.

    The reference cards all frame the sofa this way. Height is driven by the
    sofa plus its shadow rather than by the sofa alone, so the piece sits at a
    consistent height once these are tiled in a grid.
    """
    (x0, y0, _, y1), (_, shadow_y1) = content_bounds(im, cutout)
    # Size off the sofa, not off the shadow. The shadow can trail a long way
    # below the feet, and letting it drive the square leaves the piece stranded
    # in the top half of the frame with dead space under it.
    side = int((y1 - y0) * (1 + 3 * margin))
    bottom = min(shadow_y1, int(y1 + side * margin * 1.6))
    left = int(x0 - side * margin)
    top = bottom - side
    canvas = Image.new(im.mode, (side, side),
                       (0, 0, 0, 0) if cutout else (255, 255, 255))
    canvas.paste(im.crop((left, top, left + side, top + side)))
    return canvas


def recolour_sofa(src_lab, alpha, target_lab):
    """Shift only the masked fabric to the target colour, keeping its shading."""
    w = alpha.reshape(-1)
    flat = src_lab.reshape(-1, 3)
    tot = w.sum()
    mean = (flat * w[:, None]).sum(0) / max(tot, 1e-6)   # fabric-only mean
    return swatch.recolour(src_lab, mean, target_lab)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="sofa render to recolour")
    ap.add_argument("--collection", required=True, help="manifest key, e.g. manila")
    ap.add_argument("--out", default="assets/sofa")
    ap.add_argument("--size", type=int, default=1200)
    ap.add_argument("--limit", type=int, default=0, help="0 = all colours")
    ap.add_argument("--crop-left", action="store_true",
                    help="square crop showing the left of the sofa, running "
                         "off the right edge -- matches the reference cards")
    ap.add_argument("--margin", type=float, default=0.06,
                    help="left/bottom breathing room, as a fraction of the crop")
    args = ap.parse_args()

    manifest = json.load(open(os.path.join(ROOT, "assets", "swatches",
                                           "manifest.json")))
    data = manifest[args.collection]
    outdir = os.path.join(ROOT, args.out)
    os.makedirs(outdir, exist_ok=True)

    im = Image.open(os.path.join(ROOT, args.source))
    cutout = im.mode in ("RGBA", "LA") or "transparency" in im.info
    im = im.convert("RGBA" if cutout else "RGB")

    if args.crop_left:
        im = crop_left_square(im, cutout, args.margin)
    if args.size and max(im.size) > args.size:
        im = im.resize((args.size, args.size * im.size[1] // im.size[0]),
                       Image.LANCZOS)

    arr = np.asarray(im, dtype=np.float32) / 255.0
    src, base_a = (arr[..., :3], arr[..., 3]) if cutout else (arr, None)
    lab = swatch.rgb_to_lab(src)
    alpha = upholstery_mask(
        lab, CHROMA_RAMP_CUTOUT if cutout else CHROMA_RAMP_FLAT, base_a)
    covered = 100 * alpha.sum() / (base_a > 0.99).sum() if cutout else \
        100 * alpha.mean()
    print(f"{'cutout' if cutout else 'flat'} source; fabric mask covers "
          f"{covered:.1f}% of {'the sofa' if cutout else 'frame'}")

    colours = data["colors"][:args.limit] if args.limit else data["colors"]
    for c in colours:
        target = swatch.hex_to_lab(c["hex"])
        out = recolour_sofa(lab, alpha, target)
        # Composite over the untouched original so legs, shadow and any
        # non-fabric part of the render survive byte for byte.
        comp = src * (1 - alpha[..., None]) + out * alpha[..., None]
        comp = np.clip(comp, 0, 1)
        if cutout:
            # Carry the render's own alpha through untouched -- that channel is
            # where the contact shadow lives, and it must not pick up the colour.
            rgba = np.dstack([comp, base_a])
            Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA") \
                .save(os.path.join(outdir, f"{args.collection}-{c['code']}.png"))
        else:
            Image.fromarray((comp * 255 + 0.5).astype(np.uint8)) \
                .save(os.path.join(outdir, f"{args.collection}-{c['code']}.jpg"),
                      quality=92, subsampling=0)
    print(f"wrote {len(colours)} sofas to {args.out}/")


if __name__ == "__main__":
    main()

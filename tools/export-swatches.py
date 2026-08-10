#!/usr/bin/env python3
"""
Export every Ixaria colour as a recoloured fabric photo.

One source photo per material. For each colour the photo's light and shadow are
kept exactly as shot and only the hue is replaced:

    out = hex x (pixel / average)

Because the luminance map is normalised to a mean of 1.0, each rendered swatch
averages to its true hex, so the colour reference stays accurate.

This mirrors fabric-tint-lab.html pixel for pixel. Change a constant here and
change it there too, or the preview and the exported files will drift apart.

    .venv-export/bin/python tools/export-swatches.py
"""

import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURES = os.path.join(ROOT, "assets", "textures")
OUTDIR = os.path.join(ROOT, "assets", "swatches")

# Output geometry. 16:9 to match how the fabrics were shot.
WIDTH, HEIGHT = 1024, 576
JPEG_QUALITY = 90

# Also emit a small version for grid/chip use, so the config screen does not
# have to download 1024px files to draw a 120px chip.
THUMB_WIDTH = 320

# Drop-in replacements for the swatches already in assets/: same 160x160 square
# PNG, same <assetSlug>-<code>.png name, so the folder can be copied straight
# over the old files with no code change.
DROPIN_SIZE = 160

DESAT = 0.035          # pull 3.5% of saturation out; dyed fibre scatters light
SHEEN_GAIN = 40.0      # converts the sheen slider into 0-255 space

# finish -> sheen multiplier. Manila / Maya / Zoya share a photo, not a finish.
FINISH_SHEEN = {"Matte": 0.45, "Semi-Glossy": 0.85, "Glossy": 1.25}

# collection -> (source photo, contrast, sheen)
MATERIALS = {
    "enjoylux": ("src-neted-enjoylux.webp", 1.00, 0.10),
    # Milton is a smooth semi-gloss microfibre. The Arezzo shot is a coarse
    # weave, i.e. the wrong fabric, so share Enjoy Lux's smooth photo and let
    # the higher sheen carry the semi-gloss difference until a Milton shot
    # exists. src-neted-milton.webp is still on disk if you want it back.
    "milton":   ("src-neted-enjoylux.webp", 1.00, 0.35),
    "piano":    ("src-catifea.jpg",         0.70, 0.80),
    "manila":   ("src-efectcatifea.jpg",    1.00, 0.45),
    "maya":     ("src-efectcatifea.jpg",    1.00, 0.45),
    "zoya":     ("src-efectcatifea.jpg",    1.00, 0.45),
    "luna":     ("src-texturat-luna.webp",  1.00, 0.12),
    "spello":   ("src-texturat-spello.webp", 1.00, 0.12),
}


def load_collections():
    """Pull COLLECTIONS out of the generated JS the lab page already uses."""
    path = os.path.join(ROOT, "assets", "collections.js")
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    return json.loads(src[src.index("{"): src.rindex("}") + 1])


def luminance_map(path, width, height):
    """Photo -> light-and-shadow map at width x height, normalised to mean 1.0."""
    img = Image.open(path).convert("RGB")

    # cover-fit: keep the whole picture, never stretch the weave
    scale = max(width / img.width, height / img.height)
    resized = img.resize(
        (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
        Image.LANCZOS,
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    a = np.asarray(resized.crop((left, top, left + width, top + height)), dtype=np.float64)

    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    return lum / (lum.mean() or 1.0)


def srgb_lum(hexstr):
    r, g, b = (int(hexstr[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def recolour(lum, hexstr, contrast, sheen, finish):
    r0, g0, b0 = (float(int(hexstr[i:i + 2], 16)) for i in (1, 3, 5))
    L = srgb_lum(hexstr)

    # Contrast stays flat across colours. Attenuating it for dark hexes is what
    # flattens the texture; dark colours read through highlights instead, so
    # they get more additive sheen.
    v = 1.0 + (lum - 1.0) * contrast
    v /= (v.mean() or 1.0)

    s = sheen * FINISH_SHEEN[finish] * (1.9 - 1.2 * L) * SHEEN_GAIN
    add = np.where(v > 1.0, (v - 1.0) * s, 0.0)

    rgb = np.stack([
        np.clip(r0 * v + add, 0, 255),
        np.clip(g0 * v + add, 0, 255),
        np.clip(b0 * v + add, 0, 255),
    ], axis=-1)

    # desaturate toward each pixel's own luminance so brightness is unchanged
    y = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2])[..., None]
    rgb += (y - rgb) * DESAT

    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


def main():
    collections = load_collections()
    os.makedirs(OUTDIR, exist_ok=True)
    os.makedirs(os.path.join(OUTDIR, "thumb"), exist_ok=True)

    os.makedirs(os.path.join(OUTDIR, "dropin"), exist_ok=True)

    manifest = {}
    total = 0

    for key, coll in collections.items():
        if key not in MATERIALS:
            print(f"  ! no material mapped for {key}, skipped", file=sys.stderr)
            continue
        filename, contrast, sheen = MATERIALS[key]
        src = os.path.join(TEXTURES, filename)
        if not os.path.exists(src):
            print(f"  ! missing photo {filename} for {key}, skipped", file=sys.stderr)
            continue

        slug = coll.get("assetSlug") or key
        lum = luminance_map(src, WIDTH, HEIGHT)
        lum_sq = luminance_map(src, DROPIN_SIZE, DROPIN_SIZE)
        entries = []

        for code, hexstr in coll["colors"]:
            img = recolour(lum, hexstr, contrast, sheen, coll["finish"])
            name = f"{key}-{code}.jpg"

            img.save(os.path.join(OUTDIR, name), quality=JPEG_QUALITY, optimize=True)
            thumb = img.resize(
                (THUMB_WIDTH, round(THUMB_WIDTH * HEIGHT / WIDTH)), Image.LANCZOS
            )
            thumb.save(os.path.join(OUTDIR, "thumb", name), quality=JPEG_QUALITY, optimize=True)

            # drop-in: square, PNG, named exactly like the file it replaces
            sq = recolour(lum_sq, hexstr, contrast, sheen, coll["finish"])
            dropin_name = f"{slug}-{code}.png"
            sq.save(os.path.join(OUTDIR, "dropin", dropin_name), optimize=True)

            entries.append({"code": code, "hex": hexstr,
                            "file": name, "dropin": dropin_name})
            total += 1

        manifest[key] = {
            "name": coll["name"],
            "assetSlug": slug,
            "material": coll["material"],
            "finish": coll["finish"],
            "source": filename,
            "colors": entries,
        }
        print(f"  {coll['name']:<10} {len(entries):>3} swatches  "
              f"{slug}-*.png  <- {filename}")

    with open(os.path.join(OUTDIR, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)

    print(f"\n{total} swatches + thumbs -> {OUTDIR}")


if __name__ == "__main__":
    main()

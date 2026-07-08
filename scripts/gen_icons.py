#!/usr/bin/env python3
"""Generate the PWA / apple-touch icons for docs/icons/.

Draws a gold king glyph on the brand-dark background so the installed app and
the iOS home-screen bookmark get real raster icons (an SVG-only manifest is not
reliably installable and has no maskable variant). Re-run after a brand change:

    python3 scripts/gen_icons.py

Deterministic: same output every run, so committing the PNGs is safe.
"""
import os

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
KING = "♚"                       # filled king silhouette (legible at small sizes)
GOLD = (240, 192, 64, 255)            # brand --gold #f0c040
BG_CENTER = (13, 17, 23)              # #0d1117
BG_EDGE = (6, 9, 15)                  # #06090f (manifest background_color)
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "icons")
SS = 4                                # supersample factor for crisp edges


def _radial_bg(size):
    """Dark radial background, lighter center to brand-dark edge."""
    img = Image.new("RGBA", (size, size))
    px = img.load()
    cx = cy = size / 2
    maxd = (size / 2) * 1.42
    for y in range(size):
        for x in range(size):
            d = min(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / maxd, 1.0)
            r = round(BG_CENTER[0] + (BG_EDGE[0] - BG_CENTER[0]) * d)
            g = round(BG_CENTER[1] + (BG_EDGE[1] - BG_CENTER[1]) * d)
            b = round(BG_CENTER[2] + (BG_EDGE[2] - BG_CENTER[2]) * d)
            px[x, y] = (r, g, b, 255)
    return img


def _draw_king(img, glyph_frac):
    """Center the king glyph at glyph_frac of the canvas height."""
    size = img.width
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, int(size * glyph_frac))
    bx0, by0, bx1, by1 = draw.textbbox((0, 0), KING, font=font)
    w, h = bx1 - bx0, by1 - by0
    x = (size - w) / 2 - bx0
    y = (size - h) / 2 - by0
    draw.text((x, y), KING, font=font, fill=GOLD)
    return img


def make(name, size, glyph_frac, ring=False):
    big = size * SS
    img = _radial_bg(big)
    if ring:
        d = ImageDraw.Draw(img)
        pad = big * 0.055
        d.rounded_rectangle([pad, pad, big - pad, big - pad],
                            radius=big * 0.22, outline=(240, 192, 64, 90),
                            width=max(2, int(big * 0.012)))
    _draw_king(img, glyph_frac)
    img = img.resize((size, size), Image.LANCZOS)
    path = os.path.join(OUT_DIR, name)
    img.save(path, "PNG", optimize=True)
    print(f"wrote {path} ({size}x{size})")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    # "any" icons: glyph fills ~0.66, subtle gold ring inside the corners.
    make("icon-192.png", 192, 0.66, ring=True)
    make("icon-512.png", 512, 0.66, ring=True)
    # maskable: full-bleed background, glyph inside the ~0.6 safe zone, no ring.
    make("icon-512-maskable.png", 512, 0.56, ring=False)
    # apple-touch: iOS rounds the corners itself, so no ring, glyph a touch larger.
    make("apple-touch-icon.png", 180, 0.68, ring=False)


if __name__ == "__main__":
    main()

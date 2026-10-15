"""Create docs/preview.png (the link-preview card) and docs/favicon.svg (the tab icon).

Run once from the project folder:  python make_preview.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DOCS = Path("docs")
W, H = 1200, 627
S = 2  # draw at double size, then shrink, for smooth edges
INK, MUTED, RED = "#1c1917", "#6b6560", "#b91c1c"

# Windows fonts first, then Linux/Mac fallbacks
SERIF_BOLD = ["C:/Windows/Fonts/georgiab.ttf", "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
              "/Library/Fonts/Georgia Bold.ttf"]
SANS = ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/Library/Fonts/Arial.ttf"]
SANS_BOLD = ["C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
             "/Library/Fonts/Arial Bold.ttf"]


def font(paths, size):
    for path in paths:
        try:
            return ImageFont.truetype(path, size * S)
        except OSError:
            continue
    return ImageFont.load_default(size * S)


img = Image.new("RGB", (W * S, H * S), "#faf9f6")
d = ImageDraw.Draw(img)


def centered(y, text, fnt, fill, spacing=0):
    if spacing:
        widths = [d.textlength(c, font=fnt) for c in text]
        x = (W * S - sum(widths) - spacing * S * (len(text) - 1)) / 2
        for c, w in zip(text, widths):
            d.text((x, y * S), c, font=fnt, fill=fill)
            x += w + spacing * S
    else:
        d.text(((W * S - d.textlength(text, font=fnt)) / 2, y * S), text, font=fnt, fill=fill)


# Shield with a check mark
cx, top, sw, sh = W * S / 2, 70 * S, 76 * S, 90 * S
d.polygon([(cx - sw / 2, top), (cx + sw / 2, top), (cx + sw / 2, top + sh * 0.5),
           (cx, top + sh), (cx - sw / 2, top + sh * 0.5)], fill=RED)
d.line([(cx - 18 * S, top + 44 * S), (cx - 4 * S, top + 58 * S), (cx + 20 * S, top + 30 * S)],
       fill="#ffffff", width=9 * S, joint="curve")

centered(185, "AI-CURATED  \u00b7  UPDATED EVERY MORNING AT 4:30 AM ET", font(SANS, 22), MUTED, spacing=2)

title_font = font(SERIF_BOLD, 78)
while d.textlength("The Daily Security Briefing", font=title_font) > 1080 * S:  # keep it inside the card
    title_font = font(SERIF_BOLD, int(title_font.size / S) - 2)
centered(228, "The Daily Security Briefing", title_font, INK)

d.line([(150 * S, 340 * S), (1050 * S, 340 * S)], fill=INK, width=3 * S)
d.line([(150 * S, 348 * S), (1050 * S, 348 * S)], fill=INK, width=1 * S)
centered(378, "Which security news matters today, and what to do about it.", font(SANS, 30), INK)
centered(424, "In plain English, for everyone.", font(SANS, 30), MUTED)

# Severity labels
chips = [("Critical", RED), ("High", "#c2410c"), ("Medium", "#a16207"), ("Low", "#1d4ed8"), ("Info", "#57534e")]
cf, pad, gap = font(SANS_BOLD, 22), 22 * S, 14 * S
widths = [d.textlength(t, font=cf) + 2 * pad for t, _ in chips]
x = (W * S - sum(widths) - gap * (len(chips) - 1)) / 2
for (label, color), w in zip(chips, widths):
    d.rounded_rectangle([x, 500 * S, x + w, 546 * S], radius=8 * S, fill=color)
    d.text((x + pad, 511 * S), label, font=cf, fill="#ffffff")
    x += w + gap
d.rectangle([0, (H - 10) * S, W * S, H * S], fill=RED)

DOCS.mkdir(exist_ok=True)
img.resize((W, H), Image.LANCZOS).save(DOCS / "preview.png", optimize=True)

(DOCS / "favicon.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">\n'
    '  <path d="M32 4 L56 12 V30 C56 46 45 56 32 60 C19 56 8 46 8 30 V12 Z" fill="#b91c1c"/>\n'
    '  <path d="M21 32 L29 40 L44 23" fill="none" stroke="#fff" stroke-width="6" '
    'stroke-linecap="round" stroke-linejoin="round"/>\n'
    '</svg>\n',
    encoding="utf-8",
)
print("Created docs/preview.png and docs/favicon.svg")
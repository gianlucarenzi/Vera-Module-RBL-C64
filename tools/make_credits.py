#!/usr/bin/env python3
"""End credits as one tall PNG (white on black) for tools/make_video.sh.

  tools/make_credits.py CREDITS.txt OUT.png WIDTH HEIGHT

CREDITS.txt: "= title", "# heading", "- small line", plain lines, empty
lines for space; "@MUSIC@" becomes the lines of $MUSIC_CREDIT ("|"
separated), and its section goes away when that is empty; "@SUPPORTERS@"
becomes the names of $SUPPORTERS (default credits.lst at the top of the
repository: one name per line, "#" comments), a few per line, and its
section goes away when there are none. The header up to
the first empty line and lines starting with "#!" are comments. "@LOGOS@ a.png b.png" puts the
logos side by side on a white plate; the centre of the plate (px from the
top of the image) goes to OUT.png.stop, where the scrolling stops. Sizes
follow the video HEIGHT; every line is centred. Needs Pillow (python3-pil) and the
DejaVu fonts (fonts-dejavu-core).
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

src, out, W, H = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
FONTS = "/usr/share/fonts/truetype/dejavu/"
BOLD = ImageFont.truetype(FONTS + "DejaVuSans-Bold.ttf", int(H / 14))
HEAD = ImageFont.truetype(FONTS + "DejaVuSans-Bold.ttf", int(H / 30))
TEXT = ImageFont.truetype(FONTS + "DejaVuSans.ttf", int(H / 34))
SMALL = ImageFont.truetype(FONTS + "DejaVuSans.ttf", int(H / 42))
GREY, WHITE = (170, 170, 170), (255, 255, 255)

text = open(src, encoding="utf-8").read().split("\n\n", 1)[1]      # drop the header
music = [m.strip() for m in os.environ.get("MUSIC_CREDIT", "").split("|") if m.strip()]


def read_supporters():
    path = os.environ.get("SUPPORTERS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "credits.lst")
    if not os.path.isfile(path):
        return []
    names = []
    for ln in open(path, encoding="utf-8"):
        ln = ln.split("#", 1)[0].strip()
        if ln and ln not in names:
            names.append(ln)
    return names


def pack(names, font, width):
    """the names a few per line, " · " between them, each line within width"""
    probe_ = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    out_, cur = [], ""
    for n in names:
        nxt = cur + "  ·  " + n if cur else n
        if cur and probe_.textlength(nxt, font=font) > width:
            out_.append(cur)
            nxt = n
        cur = nxt
    if cur:
        out_.append(cur)
    return out_


def drop_section(lines):
    while lines and lines[-1] != "":                               # drop the heading too
        lines.pop()


lines = []
for raw in text.splitlines():
    if raw.startswith("#!"):
        continue
    if raw.strip() == "@MUSIC@":
        if music:
            lines += music
        else:
            drop_section(lines)
        continue
    if raw.strip() == "@SUPPORTERS@":
        names = read_supporters()
        if names:
            lines += pack(names, TEXT, W * 0.8)
        else:
            drop_section(lines)
        continue
    lines.append(raw.rstrip())

base = os.path.dirname(os.path.abspath(src))
rows = []                                   # (font, colour, text, gap before)
for ln in lines:
    if ln.startswith("@LOGOS@"):
        rows.append(("logos", [Image.open(os.path.join(base, f)).convert("RGBA") for f in ln.split()[1:]], "", H // 60))
    elif ln == "":
        rows.append((None, None, "", H // 22))
    elif ln.startswith("= "):
        rows.append((BOLD, WHITE, ln[2:], 0))
    elif ln.startswith("# "):
        rows.append((HEAD, GREY, ln[2:].upper(), H // 90))
    elif ln.startswith("- "):
        rows.append((SMALL, GREY, ln[2:], H // 90))
    else:
        rows.append((TEXT, WHITE, ln, H // 120))

LOGO_H, PAD = H // 11, H // 30            # logo height, plate padding
plate_h = LOGO_H + 2 * PAD


def row_h(font):
    if font == "logos":
        return plate_h
    return font.getbbox("Ag")[3] if font else 0


probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
height = sum(gap + row_h(font) for font, _, t, gap in rows)
img = Image.new("RGB", (W, height + 2), (0, 0, 0))
d = ImageDraw.Draw(img)
y = 0
stop = None
for font, colour, t, gap in rows:
    y += gap
    if font == "logos":
        logos = [im.resize((round(im.width * LOGO_H / im.height), LOGO_H), Image.LANCZOS) for im in colour]
        gap_x = PAD * 2
        plate_w = sum(im.width for im in logos) + gap_x * (len(logos) - 1) + 2 * PAD
        x0 = (W - plate_w) // 2
        d.rounded_rectangle((x0, y, x0 + plate_w, y + plate_h), radius=PAD // 2, fill=(255, 255, 255))
        x = x0 + PAD
        for im in logos:
            img.paste(im, (x, y + PAD), im)
            x += im.width + gap_x
        stop = y + plate_h // 2
        y += plate_h
    elif font:
        tw = probe.textlength(t, font=font)
        d.text(((W - tw) / 2, y), t, font=font, fill=colour)
        y += font.getbbox("Ag")[3]
img.save(out)
if stop is not None:
    open(out + ".stop", "w").write("%d\n" % stop)
print("%s: %dx%d%s" % (out, W, img.height, ", stop at %d" % stop if stop is not None else ""))

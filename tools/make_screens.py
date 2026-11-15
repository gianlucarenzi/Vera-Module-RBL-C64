#!/usr/bin/env python3
"""Screen images for the second part of the assembly video
(tools/render_enclosure.py, RENDER_MODE=desk): what the two monitors show.

  tools/make_screens.py OUT_DIR

  atari-basic.png  the Atari 130XE after power on: Atari BASIC, READY and the
                   cursor, light blue on blue, black border (GRAPHICS 0)
  c64-basic.png    the Commodore 64 after power on: the BASIC V2 banner,
                   READY. and the cursor, light blue on blue, light blue border
  vera-256.png     the VERA (640x480 on HDMI): its 256 default colours as a
                   16x16 grid, from the default palette of the X16 emulator

The text uses a small 5x7 dot matrix font of its own (not a ROM font), drawn
in 8x8 cells. The 8-bit screens get faint scan lines (CRT). Needs Pillow.
"""
import json
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1] if len(sys.argv) > 1 else "screens"
os.makedirs(OUT, exist_ok=True)

# 5x7 glyphs, rows top to bottom, "#" = on
GLYPHS = {
    "A": [" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "B": ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
    "C": [" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "],
    "D": ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    "E": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    "F": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "],
    "I": [" ### ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "K": ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    "L": ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    "M": ["#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"],
    "O": [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "R": ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    "S": [" ### ", "#   #", "#    ", " ### ", "    #", "#   #", " ### "],
    "T": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    "V": ["#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "],
    "Y": ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
    "0": [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    "1": ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "2": [" ### ", "#   #", "    #", "  ## ", " #   ", "#    ", "#####"],
    "3": [" ### ", "#   #", "    #", "  ## ", "    #", "#   #", " ### "],
    "4": ["   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "],
    "6": ["  ## ", " #   ", "#    ", "#### ", "#   #", "#   #", " ### "],
    "8": [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    "9": [" ### ", "#   #", "#   #", " ####", "    #", "   # ", " ##  "],
    "*": ["     ", "  #  ", "# # #", " ### ", "# # #", "  #  ", "     "],
    ".": ["     ", "     ", "     ", "     ", "     ", " ##  ", " ##  "],
    " ": ["     "] * 7,
}


def text_screen(cols, rows, lines, fg, bg, cursor):
    """cols x rows cells of 8x8 px; lines: {row: (col, text)}; cursor (col, row)"""
    im = Image.new("RGB", (cols * 8, rows * 8), bg)
    px = im.load()
    for r, (c0, text) in lines.items():
        for k, ch in enumerate(text):
            g = GLYPHS[ch]
            for gy in range(7):
                for gx in range(5):
                    if g[gy][gx] == "#":
                        px[(c0 + k) * 8 + 1 + gx, r * 8 + gy] = fg
    cx, cy = cursor
    for y in range(8):
        for x in range(8):
            px[cx * 8 + x, cy * 8 + y] = fg
    return im


def crt(screen, border, frame, scale=4):
    """the screen in its border (frame w, h in screen px), scaled up with
    faint scan lines"""
    fw, fh = frame
    im = Image.new("RGB", (fw, fh), border)
    im.paste(screen, ((fw - screen.width) // 2, (fh - screen.height) // 2))
    im = im.resize((fw * scale, fh * scale), Image.NEAREST)
    px = im.load()
    for y in range(scale - 1, im.height, scale):          # the last line of each
        for x in range(im.width):
            r, g, b = px[x, y]
            px[x, y] = (r * 3 // 4, g * 3 // 4, b * 3 // 4)
    return im


# Atari 130XE: GRAPHICS 0, 40x24, COLOR2 $94 (blue), COLOR1 $CA (light), border black
ATARI_BG, ATARI_FG = (0x1A, 0x56, 0xA8), (0x8C, 0xC6, 0xFF)
atari = text_screen(40, 24, {0: (2, "READY")}, ATARI_FG, ATARI_BG, (2, 1))
crt(atari, (0, 0, 0), (352, 232)).save(os.path.join(OUT, "atari-basic.png"))

# Commodore 64: 40x25, blue background, light blue text and border
C64_BG, C64_FG = (0x35, 0x28, 0x79), (0x6C, 0x5E, 0xB5)
c64 = text_screen(40, 25, {1: (4, "**** COMMODORE 64 BASIC V2 ****"),
                           3: (1, "64K RAM SYSTEM  38911 BASIC BYTES FREE"),
                           5: (0, "READY.")}, C64_FG, C64_BG, (0, 6))
crt(c64, C64_FG, (384, 264)).save(os.path.join(OUT, "c64-basic.png"))

# VERA: the 256 default colours (12-bit 0xRGB) as 16x16 tiles on 640x480
PALETTE = [
    0x000, 0xfff, 0x800, 0xafe, 0xc4c, 0x0c5, 0x00a, 0xee7, 0xd85, 0x640, 0xf77, 0x333, 0x777, 0xaf6, 0x08f, 0xbbb,
    0x000, 0x111, 0x222, 0x333, 0x444, 0x555, 0x666, 0x777, 0x888, 0x999, 0xaaa, 0xbbb, 0xccc, 0xddd, 0xeee, 0xfff,
    0x211, 0x433, 0x644, 0x866, 0xa88, 0xc99, 0xfbb, 0x211, 0x422, 0x633, 0x844, 0xa55, 0xc66, 0xf77, 0x200, 0x411,
    0x611, 0x822, 0xa22, 0xc33, 0xf33, 0x200, 0x400, 0x600, 0x800, 0xa00, 0xc00, 0xf00, 0x221, 0x443, 0x664, 0x886,
    0xaa8, 0xcc9, 0xfeb, 0x211, 0x432, 0x653, 0x874, 0xa95, 0xcb6, 0xfd7, 0x210, 0x431, 0x651, 0x862, 0xa82, 0xca3,
    0xfc3, 0x210, 0x430, 0x640, 0x860, 0xa80, 0xc90, 0xfb0, 0x121, 0x343, 0x564, 0x786, 0x9a8, 0xbc9, 0xdfb, 0x121,
    0x342, 0x463, 0x684, 0x8a5, 0x9c6, 0xbf7, 0x120, 0x241, 0x461, 0x582, 0x6a2, 0x8c3, 0x9f3, 0x120, 0x240, 0x360,
    0x480, 0x5a0, 0x6c0, 0x7f0, 0x121, 0x343, 0x465, 0x686, 0x8a8, 0x9ca, 0xbfc, 0x121, 0x242, 0x364, 0x485, 0x5a6,
    0x6c8, 0x7f9, 0x020, 0x141, 0x162, 0x283, 0x2a4, 0x3c5, 0x3f6, 0x020, 0x041, 0x061, 0x082, 0x0a2, 0x0c3, 0x0f3,
    0x122, 0x344, 0x466, 0x688, 0x8aa, 0x9cc, 0xbff, 0x122, 0x244, 0x366, 0x488, 0x5aa, 0x6cc, 0x7ff, 0x022, 0x144,
    0x166, 0x288, 0x2aa, 0x3cc, 0x3ff, 0x022, 0x044, 0x066, 0x088, 0x0aa, 0x0cc, 0x0ff, 0x112, 0x334, 0x456, 0x668,
    0x88a, 0x9ac, 0xbcf, 0x112, 0x224, 0x346, 0x458, 0x56a, 0x68c, 0x79f, 0x002, 0x114, 0x126, 0x238, 0x24a, 0x35c,
    0x36f, 0x002, 0x014, 0x016, 0x028, 0x02a, 0x03c, 0x03f, 0x112, 0x334, 0x546, 0x768, 0x98a, 0xb9c, 0xdbf, 0x112,
    0x324, 0x436, 0x648, 0x85a, 0x96c, 0xb7f, 0x102, 0x214, 0x416, 0x528, 0x62a, 0x83c, 0x93f, 0x102, 0x204, 0x306,
    0x408, 0x50a, 0x60c, 0x70f, 0x212, 0x434, 0x646, 0x868, 0xa8a, 0xc9c, 0xfbe, 0x211, 0x423, 0x635, 0x847, 0xa59,
    0xc6b, 0xf7d, 0x201, 0x413, 0x615, 0x826, 0xa28, 0xc3a, 0xf3c, 0x201, 0x403, 0x604, 0x806, 0xa08, 0xc09, 0xf0b,
]
assert len(PALETTE) == 256
vera = Image.new("RGB", (640, 480), (0, 0, 0))
vp = vera.load()
for i, c in enumerate(PALETTE):
    rgb = tuple(((c >> s) & 15) * 17 for s in (8, 4, 0))
    x0, y0 = (i % 16) * 40, (i // 16) * 30
    for y in range(y0, y0 + 30):
        for x in range(x0, x0 + 40):
            vp[x, y] = rgb
vera.resize((1280, 960), Image.NEAREST).save(os.path.join(OUT, "vera-256.png"))
# the same on a 16:9 flat monitor (1920x1080): 4:3 in the middle, black bars
wide = Image.new("RGB", (1920, 1080), (0, 0, 0))
wide.paste(vera.resize((1440, 1080), Image.NEAREST), (240, 0))
wide.save(os.path.join(OUT, "vera-256-wide.png"))


# ---------------------------------------------------------------- keyboards
# A Keyboard Layout Editor JSON (keyboard-layout-editor.com) as a list of
# keys (position and size in units, legends) for the keycaps of the render,
# and the legends drawn on one texture, the keys seen from above: 1 unit is
# U px, the keyboard is the box of its keys.
U = 228                                    # px per unit (12 px/mm)
# DejaVu Sans (free); not the Gorton keycap font: it is for non-commercial use only
FONT_DIRS = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"),   # C64 Keyboard (CC0)
             "/usr/share/fonts/truetype/dejavu"]


def font(size, names=("DejaVuSans.ttf",)):
    for n in names:
        for d in FONT_DIRS:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def clean(text):
    """the legend of a KLE label without HTML; arrows the font has"""
    text = re.sub(r"<[^>]*>", "", text)
    for a, b in (("🡹", "↑"), ("🡻", "↓"), ("🡸", "←"), ("🡺", "→")):
        text = text.replace(a, b)
    return text


LOGO = "\x00logo"                          # a legend that is a picture


def kle_keys(path, rows=None):
    """[(x, y, w, h, [legend lines])] from a KLE JSON, the first `rows` rows"""
    data = json.load(open(path, encoding="utf-8"))
    keys, y = [], 0.0
    rows_ = [r for r in data if isinstance(r, list)][:rows]
    for row in rows_:
        x, w, h = 0.0, 1.0, 1.0
        for item in row:
            if isinstance(item, dict):
                x += item.get("x", 0)
                y += item.get("y", 0)
                w, h = item.get("w", 1.0), item.get("h", 1.0)
                continue
            parts = [clean(p) for p in item.split("\n")]
            # KLE places: 0 top left, 2 top right... bottom ones from 6; the
            # legends top to bottom, the order of the label lines
            lines = [p for p in parts if p.strip()]
            if not lines and item.strip():
                lines = [LOGO]                  # a logo (an icon font in KLE)
            keys.append((x, y, w, h, lines))
            x += w
            w, h = 1.0, 1.0
        y += 1
    return keys


def keyboard_texture(keys, name, fg, inset=0.17, scale=1.0, bold=False, face=None, missing="", fixed=None):
    """legends on a transparent texture (the cap colour is the material's),
    each key's lines centred on its top face; `scale` and `bold` for keys
    seen from far or slanted (the tall sculpted caps of the C64), the lines
    shrunk to fit the key; `face` another font (file names), the lines with
    a character of `missing` (not in it) in DejaVu; `fixed` one size for all
    (units), not by the length of the legend"""
    dejavu = ("DejaVuSans-Bold.ttf",) if bold else ("DejaVuSans.ttf",)
    face = face or dejavu
    W = int(max(k[0] + k[2] for k in keys) * U)
    H = int(max(k[1] + k[3] for k in keys) * U)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x, y, w, h, lines in keys:
        lines = [l for l in lines if l != LOGO]   # not drawn here
        if not lines:
            continue
        cx, cy = (x + w / 2) * U, (y + h / 2) * U
        size = int(scale * U * (fixed if fixed else 0.30 if len(lines) == 1 and len(lines[0]) <= 2 else 0.15 if max(len(l) for l in lines) > 5 else 0.20))
        widest = max(d.textlength(l, font=font(size, face)) for l in lines)
        if widest > (w - 2 * inset) * U:
            size = int(size * (w - 2 * inset) * U / widest)
        f = font(size, face)
        lh = size * 1.15
        top = cy - lh * len(lines) / 2
        for i, line in enumerate(lines):
            lf = font(size, dejavu) if any(a in line for a in missing) else f
            tw = d.textlength(line, font=lf)
            d.text((cx - tw / 2, top + i * lh), line, font=lf, fill=fg)
    im.save(os.path.join(OUT, name + ".png"))
    json.dump({"unit_px": U, "keys": [[x, y, w, h, lines] for x, y, w, h, lines in keys]},
              open(os.path.join(OUT, name + ".json"), "w"), ensure_ascii=False, indent=0)


def legends_from_print(pdf, origin, unit, keys, name, colour, dpi=600, inset=0.12, light=False):
    """the legends of a keycap print sheet (a PDF or PDF-compatible .ai,
    rasterised with pdftoppm at `dpi`): `origin` the top left corner (px) of
    key (0, 0) of `keys`, `unit` px per unit. Black legends on white keys
    (or white on grey with `light`) become `colour` on a transparent
    texture; only each key's top face (the cell less `inset` units) is kept,
    not the outlines and the red size notes of the sheet"""
    tmp = os.path.join(OUT, ".print")
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-singlefile", pdf, tmp], check=True)
    src = Image.open(tmp + ".png").convert("RGB")
    os.remove(tmp + ".png")
    W = int(max(k[0] + k[2] for k in keys) * U)
    H = int(max(k[1] + k[3] for k in keys) * U)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for x, y, w, h, lines in keys:
        if not lines:                       # e.g. the spacebar: the sheet may differ there
            continue
        box = (origin[0] + (x + inset) * unit, origin[1] + (y + inset) * unit,
               origin[0] + (x + w - inset) * unit, origin[1] + (y + h - inset) * unit)
        cell = src.crop(tuple(int(round(v)) for v in box))
        cw, ch = int(round((w - 2 * inset) * U)), int(round((h - 2 * inset) * U))
        cell = cell.resize((cw, ch), Image.LANCZOS)
        a = Image.new("L", cell.size)
        cp, ap = cell.load(), a.load()
        for j in range(ch):
            for i in range(cw):
                r, g, b = cp[i, j]
                if r > 150 and g < 110:                        # red notes
                    continue
                v = (r + g + b) / 3
                ap[i, j] = int(max(0, min(255, (v - 170) * 3))) if light else int(max(0, min(255, (200 - v) * 1.6)))
        layer = Image.new("RGBA", cell.size, colour)
        layer.putalpha(a)
        out.alpha_composite(layer, (int(round((x + inset) * U)), int(round((y + inset) * U))))
    out.save(os.path.join(OUT, name + ".png"))
    json.dump({"unit_px": U, "keys": [[x, y, w, h, lines] for x, y, w, h, lines in keys]},
              open(os.path.join(OUT, name + ".json"), "w"), ensure_ascii=False, indent=0)


HERE = os.path.dirname(os.path.abspath(__file__))
# Atari 130XE: the first five rows of the layout (the 9U spacebar) and the
# five function keys: black legends on the white keys, white on the grey
# function keys. Drawn here (DejaVu Sans); XE_KEYS_PRINT may name a keycap
# print sheet to take the legends from instead. From the keycap print sheet ATXE.ai of
# 3DRepo (XE_KEYS_PRINT, the original legends) when there is one, else drawn
# here from the layout. ATXE.ai at 600 dpi: key ESC at (240, 744) px, HELP at
# (2924, 180) px, 337.1 px per unit.
xe = kle_keys(os.path.join(HERE, "keyboards", "atari-xe-style.json"), rows=5)
fn = [(i * 1.5, 0, 1.5, 1, [t]) for i, t in enumerate(("Help", "Start", "Select", "Option", "Reset"))]
WHITE = (245, 245, 240, 255)
BLACK = (22, 22, 24, 255)
sheet = os.environ.get("XE_KEYS_PRINT")
if sheet and os.path.isfile(sheet):
    legends_from_print(sheet, (240, 744), 337.1, xe, "xe-keys", BLACK)
    legends_from_print(sheet, (2924, 180), 337.1, fn, "xe-fn", WHITE, light=True)
else:
    keyboard_texture(xe, "xe-keys", BLACK)
    keyboard_texture(fn, "xe-fn", WHITE, fixed=0.17)
# Commodore 64 (breadbin): almost black brown keys and dark grey function
# keys (the column on the right, x > 16 units), white legends
c64 = kle_keys(os.path.join(HERE, "keyboards", "commodore-64.json"), rows=5)
# the C64 font has capitals only: the lines with the lower case f1 ... f8 of
# the function keys (and the arrows it lacks) in DejaVu
C64_FONT = dict(face=("C64Keyboard-Regular.otf",), missing="↕↔f", scale=1.6)
keyboard_texture([k for k in c64 if k[0] < 16], "c64-keys", WHITE, **C64_FONT)
keyboard_texture([k for k in c64 if k[0] >= 16], "c64-fn", WHITE, **C64_FONT)
print("written", ", ".join(sorted(os.listdir(OUT))))

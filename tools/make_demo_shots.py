#!/usr/bin/env python3
"""Illustrative 320x240 'screenshots' of two ORIGINAL demo games for the VERA
module READMEs (they are mock-ups, not captures from the board):

  CIRCUIT RUNNER  maze-chase: a little robot collects solder pads on a
                  PCB-shaped maze, chased by bugs
  IRONHOLD        side-scrolling fantasy action: an axe warrior in front of
                  a castle at sunset

usage: make_shots.py OUTDIR PLATFORM [PLATFORM ...]   (e.g. "APPLE II")
"""
import math
import os
import random
import sys

from PIL import Image, ImageDraw

W, H, SCALE = 320, 240, 3

# ---------------------------------------------------------------- 5x7 font
FONT = {
    'A': "01110 10001 10001 11111 10001 10001 10001", 'B': "11110 10001 10001 11110 10001 10001 11110",
    'C': "01110 10001 10000 10000 10000 10001 01110", 'D': "11110 10001 10001 10001 10001 10001 11110",
    'E': "11111 10000 10000 11110 10000 10000 11111", 'F': "11111 10000 10000 11110 10000 10000 10000",
    'G': "01110 10001 10000 10111 10001 10001 01111", 'H': "10001 10001 10001 11111 10001 10001 10001",
    'I': "01110 00100 00100 00100 00100 00100 01110", 'J': "00111 00010 00010 00010 00010 10010 01100",
    'K': "10001 10010 10100 11000 10100 10010 10001", 'L': "10000 10000 10000 10000 10000 10000 11111",
    'M': "10001 11011 10101 10101 10001 10001 10001", 'N': "10001 11001 10101 10011 10001 10001 10001",
    'O': "01110 10001 10001 10001 10001 10001 01110", 'P': "11110 10001 10001 11110 10000 10000 10000",
    'Q': "01110 10001 10001 10001 10101 10010 01101", 'R': "11110 10001 10001 11110 10100 10010 10001",
    'S': "01111 10000 10000 01110 00001 00001 11110", 'T': "11111 00100 00100 00100 00100 00100 00100",
    'U': "10001 10001 10001 10001 10001 10001 01110", 'V': "10001 10001 10001 10001 10001 01010 00100",
    'W': "10001 10001 10001 10101 10101 10101 01010", 'X': "10001 10001 01010 00100 01010 10001 10001",
    'Y': "10001 10001 01010 00100 00100 00100 00100", 'Z': "11111 00001 00010 00100 01000 10000 11111",
    '0': "01110 10001 10011 10101 11001 10001 01110", '1': "00100 01100 00100 00100 00100 00100 01110",
    '2': "01110 10001 00001 00010 00100 01000 11111", '3': "11110 00001 00001 01110 00001 00001 11110",
    '4': "00010 00110 01010 10010 11111 00010 00010", '5': "11111 10000 11110 00001 00001 10001 01110",
    '6': "00110 01000 10000 11110 10001 10001 01110", '7': "11111 00001 00010 00100 01000 01000 01000",
    '8': "01110 10001 10001 01110 10001 10001 01110", '9': "01110 10001 10001 01111 00001 00010 01100",
    ' ': "00000 00000 00000 00000 00000 00000 00000", '-': "00000 00000 00000 11111 00000 00000 00000",
    ':': "00000 01100 01100 00000 01100 01100 00000", '.': "00000 00000 00000 00000 00000 01100 01100",
    '!': "00100 00100 00100 00100 00100 00000 00100", '/': "00001 00010 00010 00100 01000 01000 10000",
    '(': "00010 00100 01000 01000 01000 00100 00010", ')': "01000 00100 00010 00010 00010 00100 01000",
}


def text(im, x, y, s, col, shadow=None, size=1):
    px = im.load()
    for ch in s.upper():
        rows = FONT.get(ch, FONT[' ']).split()
        for r, row in enumerate(rows):
            for c, bit in enumerate(row):
                if bit == '1':
                    for dy in range(size):
                        for dx in range(size):
                            X, Y = x + c * size + dx, y + r * size + dy
                            if shadow and 0 <= X + 1 < W and 0 <= Y + 1 < H:
                                px[X + 1, Y + 1] = shadow
                            if 0 <= X < W and 0 <= Y < H:
                                px[X, Y] = col
        x += 6 * size
    return x


def text_w(s, size=1):
    return len(s) * 6 * size - size


def sprite(im, x, y, rows, pal):
    """rows: strings, '.' transparent, other chars index pal"""
    px = im.load()
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch != '.' and 0 <= x + c < W and 0 <= y + r < H:
                px[x + c, y + r] = pal[ch]


def save(im, path):
    im.resize((W * SCALE, H * SCALE), Image.NEAREST).save(path)


# ---------------------------------------------------------------- CIRCUIT RUNNER
MAZE = [
    "########################################",
    "#o.................##.................o#",
    "#.####.#######.###.##.###.#######.####.#",
    "#.####.#######.###.##.###.#######.####.#",
    "#......................................#",
    "#.####.##.###########.#######.##.####..#",
    "#......##......##.........##..##.......#",
    "######.#####.#.##.#######.##.###.#######",
    "     #.##....#.............#....##.#    ",
    "######.##.####.####   ####.####.##.#####",
    "#.........#....#         #....#........#",
    "#.#######.#.##.#         #.##.#.######.#",
    "#.#.......#.##.###########.##.#......#.#",
    "#.#.#####.#....................#####.#.#",
    "#...#   #.####.##.#######.##.###   #...#",
    "###.#####......##....#....##......####.#",
    "#o.........###.#####.#.#####.###......o#",
    "#.########.###.......#.......###.#####.#",
    "#.........................  ...........#",
    "########################################",
]


def circuit_runner(platform, seed=7):
    random.seed(seed)
    im = Image.new('RGB', (W, H), (6, 22, 14))
    d = ImageDraw.Draw(im)
    # PCB texture: faint grid of vias
    for y in range(28, 232, 8):
        for x in range(0, W, 8):
            if random.random() < 0.05:
                im.putpixel((x + 4, y + 4), (20, 60, 36))
    ox, oy, T = 0, 32, 8
    copper, copper_hi, copper_lo = (214, 150, 52), (255, 210, 110), (120, 74, 20)
    for r, row in enumerate(MAZE):
        for c, ch in enumerate(row):
            x, y = ox + c * T, oy + r * T
            if ch == '#':
                d.rectangle([x, y, x + T - 1, y + T - 1], fill=(14, 52, 30))
                # copper trace drawn along wall cells, connected to neighbours
                def wall(rr, cc):
                    return 0 <= rr < len(MAZE) and 0 <= cc < len(MAZE[0]) and MAZE[rr][cc] == '#'
                cx, cy = x + 3, y + 3
                d.rectangle([cx, cy, cx + 1, cy + 1], fill=copper)
                if wall(r, c + 1):
                    d.rectangle([cx, cy, x + T - 1, cy + 1], fill=copper)
                if wall(r, c - 1):
                    d.rectangle([x, cy, cx + 1, cy + 1], fill=copper)
                if wall(r + 1, c):
                    d.rectangle([cx, cy, cx + 1, y + T - 1], fill=copper)
                if wall(r - 1, c):
                    d.rectangle([cx, y, cx + 1, cy + 1], fill=copper)
                im.putpixel((cx, cy), copper_hi)
            elif ch == '.':
                # solder pad
                d.rectangle([x + 3, y + 3, x + 4, y + 4], fill=(200, 200, 210))
                im.putpixel((x + 3, y + 3), (255, 255, 255))
            elif ch == 'o':
                # chip power-up
                d.rectangle([x + 1, y + 2, x + 6, y + 5], fill=(30, 30, 36))
                for k in range(2, 6):
                    im.putpixel((x + k, y + 1), (190, 190, 200))
                    im.putpixel((x + k, y + 6), (190, 190, 200))
                im.putpixel((x + 2, y + 3), (90, 230, 255))
    # player: little blue robot with antenna
    robot = [
        "...c....",
        "..bbbb..",
        ".bwbbwb.",
        ".bbbbbb.",
        "..bddb..",
        ".bbbbbb.",
        ".b.bb.b.",
        "..b..b..",
    ]
    sprite(im, ox + 17 * T, oy + 18 * T, robot, {'b': (70, 150, 255), 'w': (255, 255, 255),
                                                 'd': (20, 40, 90), 'c': (255, 80, 80)})
    # trail of eaten pads (empty) behind the robot already handled by maze gaps
    bug = [
        "y......y",
        ".y.rr.y.",
        "..rrrr..",
        ".rkrrkr.",
        "rrrrrrrr",
        ".rrrrrr.",
        "r.r..r.r",
        "........",
    ]
    for (cx, cy, body) in ((8, 10, (230, 60, 60)), (31, 10, (240, 140, 30)),
                           (20, 13, (190, 70, 220)), (5, 4, (60, 210, 120))):
        sprite(im, ox + cx * T, oy + cy * T, bug, {'r': body, 'y': (255, 230, 120), 'k': (10, 10, 10)})
    # bottom HUD: lives as robot heads
    d.rectangle([0, 0, W - 1, 30], fill=(4, 10, 8))
    d.line([0, 30, W - 1, 30], fill=copper_lo)
    text(im, 6, 4, "CIRCUIT RUNNER", (255, 210, 110), (60, 30, 0), 1)
    text(im, 6, 16, "1UP 004270", (230, 230, 240))
    hs = "HI 018500"
    text(im, (W - text_w(hs)) // 2, 16, hs, (230, 230, 240))
    tag = "VERA - " + platform
    text(im, W - text_w(tag) - 6, 4, tag, (90, 230, 255))
    for k in range(3):
        sprite(im, W - 14 - k * 11, 15, robot, {'b': (70, 150, 255), 'w': (255, 255, 255),
                                                'd': (20, 40, 90), 'c': (255, 80, 80)})
    # footer
    fy = oy + len(MAZE) * T + 6
    d.rectangle([0, fy, W - 1, H - 1], fill=(4, 10, 8))
    d.line([0, fy, W - 1, fy], fill=copper_lo)
    text(im, 6, fy + 8, "LEVEL 03", (230, 230, 240))
    s = "BUGS SQUASHED 012"
    text(im, (W - text_w(s)) // 2, fy + 8, s, (230, 230, 240))
    s = "CHIPS 2/4"
    text(im, W - text_w(s) - 6, fy + 8, s, (90, 230, 255))
    for k in range(4):
        x = 6 + k * 12
        col = (90, 230, 255) if k < 2 else (40, 60, 70)
        d.rectangle([x, fy + 20, x + 8, fy + 25], fill=(30, 30, 36))
        im.putpixel((x + 2, fy + 22), col)
    return im


# ---------------------------------------------------------------- IRONHOLD
def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ironhold(platform, title=False, seed=3):
    random.seed(seed)
    im = Image.new('RGB', (W, H))
    d = ImageDraw.Draw(im)
    # sunset sky, banded like a 4096-colour palette
    top, mid, low = (40, 20, 70), (170, 60, 90), (250, 170, 80)
    for y in range(0, 170):
        t = y / 170
        col = lerp(top, mid, t / 0.6) if t < 0.6 else lerp(mid, low, (t - 0.6) / 0.4)
        col = tuple(c // 17 * 17 for c in col)
        d.line([0, y, W, y], fill=col)
    # sun
    d.ellipse([200, 100, 250, 150], fill=(255, 220, 140))
    for y in range(118, 150, 5):
        d.line([196, y, 254, y], fill=lerp(mid, low, 0.75))
    # stars
    for _ in range(40):
        x, y = random.randrange(W), random.randrange(70)
        im.putpixel((x, y), (255, 240, 220))
    # far mountains
    pts = [(0, 150)]
    x = 0
    while x < W:
        x += random.randint(12, 30)
        pts.append((x, random.randint(105, 140)))
    pts += [(W, 170), (0, 170)]
    d.polygon(pts, fill=(80, 40, 90))
    # castle silhouette on a hill
    hill = (50, 24, 60)
    d.ellipse([20, 130, 190, 230], fill=hill)
    cast = (34, 16, 44)
    d.rectangle([60, 110, 150, 160], fill=cast)
    for tx in (52, 96, 140):
        d.rectangle([tx, 86, tx + 18, 160], fill=cast)
        for k in range(0, 18, 6):
            d.rectangle([tx + k, 80, tx + k + 3, 86], fill=cast)
        d.polygon([(tx - 2, 86), (tx + 9, 66), (tx + 20, 86)], fill=cast)
    for k in range(60, 150, 8):
        d.rectangle([k, 104, k + 4, 110], fill=cast)
    for wx, wy in ((58, 100), (102, 96), (146, 100), (80, 128), (124, 128)):
        d.rectangle([wx, wy, wx + 2, wy + 4], fill=(255, 200, 90))
    # mid trees
    for tx in range(-10, W, 22):
        h = random.randint(26, 40)
        base = 182
        d.polygon([(tx, base), (tx + 11, base - h), (tx + 22, base)], fill=(24, 44, 40))
    # ground: stone blocks
    d.rectangle([0, 182, W, H], fill=(70, 58, 52))
    for gy in range(182, H, 10):
        off = 0 if (gy // 10) % 2 else 10
        for gx in range(-off, W, 20):
            d.rectangle([gx, gy, gx + 19, gy + 9], outline=(40, 32, 30))
            d.line([gx + 1, gy + 1, gx + 18, gy + 1], fill=(110, 92, 80))
    d.line([0, 182, W, 182], fill=(140, 120, 90))

    pal = {'h': (190, 190, 200), 's': (230, 170, 120), 'k': (20, 12, 10), 'r': (180, 40, 40),
           'b': (120, 70, 30), 'B': (80, 44, 20), 'm': (150, 150, 160), 'M': (90, 90, 100),
           'y': (240, 200, 80), 'w': (255, 255, 255), 'g': (90, 60, 40)}
    warrior = [
        "......hhhh........",
        ".....hhhhhh.......",
        ".....hkssks....M..",
        ".....sssss....MmM.",
        "......sss.....MmM.",
        "....rrsssrr....b..",
        "...rrssssssrr..b..",
        "..ss.yyyyyy.ss.b..",
        "..ss.bbbbbb.sssb..",
        "..s..bbbbbb..ss...",
        ".....BBBBBB.......",
        ".....bb..bb.......",
        ".....bb..bb.......",
        "....ggg..ggg......",
    ]
    big = [''.join(ch * 2 for ch in row) for row in warrior for _ in range(2)]
    if not title:
        sprite(im, 90, 182 - len(big), big, pal)
        # axe swing arc
        for a in range(-60, 20, 6):
            ax = 126 + int(22 * math.cos(math.radians(a)))
            ay = 158 + int(22 * math.sin(math.radians(a)))
            im.putpixel((ax, ay), (255, 255, 220))
        lizard = [
            "....gggg....",
            "...gGggGg...",
            "...ggggggr..",
            "....ggg.....",
            "..ggggggg...",
            ".gg.ggg.gg..",
            "....g.g.....",
            "...gg.gg....",
        ]
        lz = [''.join(ch * 3 for ch in row) for row in lizard for _ in range(3)]
        sprite(im, 190, 182 - len(lz), lz, {'g': (60, 150, 70), 'G': (255, 230, 0), 'r': (220, 40, 40)})
        # coins
        for cx in (160, 172, 184):
            d.ellipse([cx, 140, cx + 6, 146], fill=(250, 210, 60), outline=(150, 100, 20))
        # HUD
        d.rectangle([0, 0, W - 1, 22], fill=(10, 6, 16))
        d.line([0, 22, W, 22], fill=(150, 110, 60))
        text(im, 6, 4, "IRONHOLD", (250, 210, 120), (80, 40, 0))
        text(im, 6, 13, "SCORE 015300", (230, 230, 240))
        text(im, 120, 4, "LIFE", (230, 230, 240))
        for k in range(10):
            col = (220, 50, 50) if k < 7 else (60, 30, 30)
            d.rectangle([150 + k * 8, 4, 155 + k * 8, 10], fill=col)
        text(im, 120, 13, "ROUND 1-2", (230, 230, 240))
        tag = "VERA - " + platform
        text(im, W - text_w(tag) - 6, 13, tag, (120, 220, 255))
    else:
        # attract / title screen
        d.rectangle([0, 0, W, H], fill=None)
        sprite(im, 140, 182 - len(big), big, pal)
        t = "IRONHOLD"
        text(im, (W - text_w(t, 4)) // 2 + 2, 26, t, (250, 200, 90), (60, 20, 10), 4)
        s = "A TALE OF AXE AND STONE"
        text(im, (W - text_w(s)) // 2, 62, s, (255, 240, 220), (40, 10, 30))
        s = "PUSH START"
        text(im, (W - text_w(s)) // 2, 200, s, (255, 255, 255), (40, 10, 30))
        s = "VERA DEMO - " + platform
        text(im, (W - text_w(s)) // 2, 222, s, (120, 220, 255), (0, 0, 0))
    return im


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for platform in sys.argv[2:]:
        slug = platform.lower().replace(' ', '')
        save(circuit_runner(platform), os.path.join(out, 'demo-circuit-runner-%s.png' % slug))
        save(ironhold(platform), os.path.join(out, 'demo-ironhold-%s.png' % slug))
        save(ironhold(platform, title=True), os.path.join(out, 'demo-ironhold-title-%s.png' % slug))
    print('written to', out)


if __name__ == '__main__':
    main()

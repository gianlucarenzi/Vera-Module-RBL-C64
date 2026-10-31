#!/usr/bin/env python3
"""Add free thermal vias inside the tabs of U13 (3V3) and U15 (GND).

Candidates on a grid inside each tab; a candidate is kept only if it clears
every other-net track, via and pad on all copper layers, and every hole.

usage: thermal_vias.py in.kicad_pcb out.kicad_pcb
"""
import math
import re
import sys

VIA, DRILL = 0.8, 0.4
CLEAR = 0.15 + 0.05      # board clearance plus margin
HOLE2HOLE = 0.25 + 0.05
# ref, pad number, rows x cols of the grid
TABS = [('U13', '2', 3, 2), ('U15', '2', 4, 4)]
INSET = 0.1              # via edge to tab edge

src, dst = sys.argv[1:3]
text = open(src).read()


def seg_point(a, b, p):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0 if l2 == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def blocks(kind):
    """Top-level (module ...) blocks with their text."""
    out, i = [], 0
    while True:
        i = text.find('\n  (%s ' % kind, i)
        if i < 0:
            return out
        d = 0
        for j in range(i + 1, len(text)):
            if text[j] == '(':
                d += 1
            elif text[j] == ')':
                d -= 1
                if d == 0:
                    break
        out.append(text[i + 1:j + 1])
        i = j


nets = {m.group(1): m.group(2) for m in re.finditer(r'^\s*\(net (\d+) "?([^")]*)"?\)\s*$', text, re.M)}
ALL = {'F.Cu', 'POWER', 'GND', 'B.Cu'}

# pads: (layers, net, kind, dist-function, hole radius)
pads = []
tabs = {}
for mod in blocks('module'):
    at = re.search(r'^\s*\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', mod, re.M)
    mx, my = float(at.group(1)), float(at.group(2))
    mr = math.radians(float(at.group(3) or 0))
    ref = re.search(r'fp_text reference (\S+)', mod).group(1)
    for p in re.finditer(r'\(pad "?([^" ]*)"? (\w+) (\w+) \(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\) \(size ([\d.]+) ([\d.]+)\)'
                         r'(.*?)(?=\n    \(pad |\n    \(model |\n  \)$|\Z)', mod, re.S):
        num, kind, shape = p.group(1), p.group(2), p.group(3)
        px, py = float(p.group(4)), float(p.group(5))
        ang = math.radians(float(p.group(6) or 0))
        w, h = float(p.group(7)), float(p.group(8))
        rest = p.group(9)
        x = mx + px * math.cos(mr) + py * math.sin(mr)
        y = my - px * math.sin(mr) + py * math.cos(mr)
        lay = set(re.search(r'\(layers ([^)]*)\)', rest).group(1).split())
        cu = ALL if (kind != 'smd' or '*.Cu' in lay) else lay & ALL
        n = re.search(r'\(net (\d+) ', rest)
        net = n.group(1) if n else None
        dr = re.search(r'\(drill (?:oval )?([\d.]+)', rest)
        hole = float(dr.group(1)) / 2 if dr else 0
        c, s = math.cos(ang), math.sin(ang)

        def dist(qx, qy, x=x, y=y, w=w, h=h, c=c, s=s, shape=shape):
            if shape == 'circle':
                return math.hypot(qx - x, qy - y) - w / 2
            dx, dy = qx - x, qy - y
            lx, ly = dx * c - dy * s, dx * s + dy * c
            ex, ey = max(abs(lx) - w / 2, 0), max(abs(ly) - h / 2, 0)
            return math.hypot(ex, ey) if ex or ey else -min(w / 2 - abs(lx), h / 2 - abs(ly))
        if cu:
            pads.append((cu, net, dist, (x, y, hole), (ref, num)))
        for tref, tnum, rows, cols in TABS:
            if ref == tref and num == tnum and w * h > 4:
                tabs[ref] = (x, y, w, h, mr + ang, net, rows, cols)

segs = [((float(m.group(1)), float(m.group(2))), (float(m.group(3)), float(m.group(4))), float(m.group(5)), m.group(6), m.group(7))
        for m in re.finditer(r'\(segment \(start ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\) \(width ([\d.]+)\) \(layer ([^)]+)\) \(net (\d+)\)', text)]
vias = [(float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4) or 0.4), m.group(5))
        for m in re.finditer(r'\(via (?:blind |micro )?\(at ([-\d.]+) ([-\d.]+)\) \(size ([\d.]+)\)(?: \(drill ([\d.]+)\))? \(layers [^)]*\) \(net (\d+)\)', text)]


def ok(x, y, net):
    r = VIA / 2
    for a, b, w, layer, n in segs:
        if n != net and seg_point(a, b, (x, y)) < r + w / 2 + CLEAR:
            return 'track %s %s' % (nets.get(n), layer)
    for vx, vy, size, drill, n in vias:
        d = math.hypot(vx - x, vy - y)
        if n != net and d < r + size / 2 + CLEAR:
            return 'via %s' % nets.get(n)
        if d - drill / 2 - DRILL / 2 < HOLE2HOLE:
            return 'hole of via %s' % nets.get(n)
    for cu, n, dist, (hx, hy, hr), who in pads:
        if n != net and dist(x, y) < r + CLEAR:
            return 'pad %s.%s' % who
        if hr and math.hypot(hx - x, hy - y) - hr - DRILL / 2 < HOLE2HOLE:
            return 'hole of pad %s.%s' % who
    return None


new = []
for ref, (cx, cy, w, h, rot, net, rows, cols) in tabs.items():
    c, s = math.cos(rot), math.sin(rot)
    span_x, span_y = w - VIA - 2 * INSET, h - VIA - 2 * INSET
    kept = []
    for i in range(rows):
        for j in range(cols):
            lx = -span_x / 2 + span_x * j / max(cols - 1, 1) if cols > 1 else 0
            ly = -span_y / 2 + span_y * i / max(rows - 1, 1) if rows > 1 else 0
            x = round(cx + lx * c + ly * s, 3)
            y = round(cy - lx * s + ly * c, 3)
            why = ok(x, y, net)
            if why:
                print('%s: skip (%.3f, %.3f): %s' % (ref, x, y, why))
            else:
                kept.append((x, y))
    for x, y in kept:
        vias.append((x, y, VIA, DRILL, net))
        new.append('  (via (at %s %s) (size %s) (drill %s) (layers F.Cu B.Cu) (net %s))' % (x, y, VIA, DRILL, net))
    print('%s (%s): %d of %d vias' % (ref, nets[net], len(kept), rows * cols))

# insert after the last via
last = max(m.end() for m in re.finditer(r'\n  \(via \(at [^\n]*', text))
text = text[:last] + '\n' + '\n'.join(new) + text[last:]
open(dst, 'w').write(text)

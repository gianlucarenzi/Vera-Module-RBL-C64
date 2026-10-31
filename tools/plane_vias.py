#!/usr/bin/env python3
"""Give every SMD pad of the plane nets its own via to the plane.

Reads the pads and the outline from the .kicad_pcb (KiCad 5) and adds to the
DSN (wiring) a fixed via plus a short stub for each SMD pad of the given nets.
Pads big enough to hold vias (exposed pads) get vias inside instead. The
router then sees these pins connected through the planes and leaves the
outer layers to the signals.

usage: plane_vias.py board.kicad_pcb in.dsn out.dsn NET[,NET...]
"""
import math
import re
import sys

CLEAR = 0.15 + 0.01        # mm, board clearance plus margin
EDGE = 0.30                # mm, copper to board edge
HOLE = 0.25                # mm, via to non-plated hole
STUB_W = 0.30              # mm, Power class width
VIAS = [(0.8, 'Via[0-3]_800:400_um'), (0.6, 'Via[0-3]_600:400_um')]


def sexp(text):
    tok = re.findall(r'"(?:[^"\\]|\\.)*"|[()]|[^\s()"]+', text)
    stack = [[]]
    for t in tok:
        if t == '(':
            stack.append([])
        elif t == ')':
            x = stack.pop()
            stack[-1].append(x)
        else:
            stack[-1].append(t[1:-1] if t.startswith('"') else t)
    return stack[0][0]


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def first(node, key):
    f = find(node, key)
    return f[0] if f else None


# ---------------------------------------------------------------- geometry

class Rect:
    """Rotated rectangle (pads are approximated by their bounding rectangle)."""

    def __init__(self, cx, cy, w, h, ang):
        self.cx, self.cy, self.hw, self.hh = cx, cy, w / 2, h / 2
        a = math.radians(ang)
        self.c, self.s = math.cos(a), math.sin(a)

    def local(self, x, y):
        dx, dy = x - self.cx, y - self.cy
        # KiCad: y down, positive angle counter-clockwise on screen
        return dx * self.c - dy * self.s, dx * self.s + dy * self.c

    def dist(self, x, y):
        lx, ly = self.local(x, y)
        ex, ey = max(abs(lx) - self.hw, 0), max(abs(ly) - self.hh, 0)
        if ex == 0 and ey == 0:
            return -min(self.hw - abs(lx), self.hh - abs(ly))
        return math.hypot(ex, ey)

    def seg_dist(self, a, b):
        # sampled: stubs are short
        n = max(2, int(math.dist(a, b) / 0.02))
        return min(self.dist(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1))


class Circle:
    def __init__(self, cx, cy, r):
        self.cx, self.cy, self.r = cx, cy, r

    def dist(self, x, y):
        return math.hypot(x - self.cx, y - self.cy) - self.r

    def seg_dist(self, a, b):
        return seg_point(a, b, (self.cx, self.cy)) - self.r


def seg_point(a, b, p):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0 if l2 == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


# ---------------------------------------------------------------- board

pcb_path, dsn_in, dsn_out, nets_arg = sys.argv[1:5]
plane_nets = nets_arg.split(',')
pcb = sexp(open(pcb_path).read())

pads = []    # dict(net, layers, shape, center, ref, area)
holes = []   # Circle of non-plated holes
for mod in find(pcb, 'module'):
    at = first(mod, 'at')
    mx, my = float(at[1]), float(at[2])
    mr = math.radians(float(at[3]) if len(at) > 3 else 0)
    ref = next(c[2] for c in find(mod, 'fp_text') if c[1] == 'reference')
    for p in find(mod, 'pad'):
        kind, shape = p[2], p[3]
        pat = first(p, 'at')
        px, py = float(pat[1]), float(pat[2])
        pang = float(pat[3]) if len(pat) > 3 else 0
        x = mx + px * math.cos(mr) + py * math.sin(mr)
        y = my - px * math.sin(mr) + py * math.cos(mr)
        size = first(p, 'size')
        w, h = float(size[1]), float(size[2])
        if kind == 'np_thru_hole':
            d = float(first(p, 'drill')[1])
            holes.append(Circle(x, y, d / 2))
            continue
        layers = first(p, 'layers')[1:]
        cu = set()
        for l in layers:
            if l in ('*.Cu', 'F&B.Cu'):
                cu |= {'F.Cu', 'B.Cu', 'IN'}
            elif l.endswith('.Cu'):
                cu.add(l)
        if kind == 'thru_hole':
            cu |= {'F.Cu', 'B.Cu', 'IN'}
        net = first(p, 'net')
        if shape == 'custom':
            # anchor plus primitives: a circle around all of them
            reach = math.hypot(w, h) / 2
            for prim in find(first(p, 'primitives') or [], 'gr_poly'):
                pw = float(first(prim, 'width')[1]) / 2 if first(prim, 'width') else 0
                for xy in find(first(prim, 'pts'), 'xy'):
                    reach = max(reach, math.hypot(float(xy[1]), float(xy[2])) + pw)
            geo = Circle(x, y, reach)
        elif shape == 'circle':
            geo = Circle(x, y, w / 2)
        else:
            geo = Rect(x, y, w, h, pang)
        pads.append(dict(ref=ref, num=p[1], kind=kind, net=net[2] if net else '', cu=cu,
                         geo=geo, x=x, y=y, w=w, h=h, ang=pang, mod=(mx, my)))

edges = []
for g in pcb:
    if not isinstance(g, list) or g[0] not in ('gr_line', 'gr_arc') or first(g, 'layer')[1] != 'Edge.Cuts':
        continue
    s, e = first(g, 'start'), first(g, 'end')
    a, b = (float(s[1]), float(s[2])), (float(e[1]), float(e[2]))
    if g[0] == 'gr_line':
        edges.append((a, b))
    else:  # arc: start = centre, end = first point, angle
        ang = math.radians(float(first(g, 'angle')[1]))
        r = math.dist(a, b)
        a0 = math.atan2(b[1] - a[1], b[0] - a[0])
        pts = [(a[0] + r * math.cos(a0 + ang * i / 16), a[1] + r * math.sin(a0 + ang * i / 16)) for i in range(17)]
        edges += list(zip(pts, pts[1:]))

placed = []   # (Circle, net)
near_pads, near_edges = pads, edges


def focus(x, y, radius=4.0):
    """Restrict the clearance checks to the copper around (x, y)."""
    global near_pads, near_edges
    near_pads = [p for p in pads if math.hypot(p['x'] - x, p['y'] - y) - max(p['w'], p['h']) < radius]
    near_edges = [e for e in edges if seg_point(e[0], e[1], (x, y)) < radius]
stubs = []    # (a, b, layer, net)


def via_ok(x, y, r, net, own):
    for e in near_edges:
        if seg_point(e[0], e[1], (x, y)) < r + EDGE:
            return False
    for h in holes:
        if h.dist(x, y) < r + HOLE:
            return False
    for p in near_pads:
        if p is own:
            continue
        # the router keeps vias clear of pads and vias even of their own net
        need = r + CLEAR
        if p['geo'].dist(x, y) < need:
            return False
    for v, n in placed:
        if v.dist(x, y) < r + CLEAR:
            return False
    for a, b, _, n in stubs:
        if n != net and seg_point(a, b, (x, y)) < r + STUB_W / 2 + CLEAR:
            return False
    return True


def stub_ok(a, b, layer, net, own):
    for p in near_pads:
        if p is own or p['net'] == net or layer not in p['cu']:
            continue
        if p['geo'].seg_dist(a, b) < STUB_W / 2 + CLEAR:
            return False
    for v, n in placed:
        if n != net and v.seg_dist(a, b) < STUB_W / 2 + CLEAR:
            return False
    return True


def place_inside(p):
    """Vias inside a large pad (exposed pad): a 2x2 grid where it fits, else one."""
    r = VIAS[1][0] / 2
    hw, hh = p['w'] / 2 - r - 0.1, p['h'] / 2 - r - 0.1
    if hw < 0 or hh < 0:
        return []
    g = p['geo']
    offs = [(-hw / 2, -hh / 2), (hw / 2, -hh / 2), (-hw / 2, hh / 2), (hw / 2, hh / 2)] if min(hw, hh) > 0.8 else [(0, 0)]
    out = []
    for lx, ly in offs:
        x = g.cx + lx * g.c + ly * g.s
        y = g.cy - lx * g.s + ly * g.c
        if via_ok(x, y, r, p['net'], p):
            out.append((x, y, VIAS[1]))
            placed.append((Circle(x, y, r), p['net']))
    return out


def place_outside(p):
    layer = next(iter(p['cu'] & {'F.Cu', 'B.Cu'}))
    best = None
    cx, cy = p['x'], p['y']
    mx, my = p['mod']
    for dia, name in VIAS:
        r = dia / 2
        for k in range(24):
            a = math.radians(k * 15)
            dx, dy = math.cos(a), math.sin(a)
            # start where the via clears the own pad by a little
            t = 0.0
            while p['geo'].dist(cx + dx * t, cy + dy * t) < r + CLEAR:
                t += 0.02
            for i in range(40):
                d = t + i * 0.05
                x, y = cx + dx * d, cy + dy * d
                if via_ok(x, y, r, p['net'], p) and stub_ok((cx, cy), (x, y), layer, p['net'], p):
                    # short stubs first; between equals, away from the part's centre
                    away = (x - mx) * dx + (y - my) * dy
                    cost = d + (0.3 if dia < 0.8 else 0) - 0.01 * (away > 0)
                    if best is None or cost < best[0]:
                        best = (cost, x, y, (dia, name), layer)
                    break
        if best and best[3][0] == dia:
            break
    if best is None:
        return None
    _, x, y, via, layer = best
    placed.append((Circle(x, y, via[0] / 2), p['net']))
    stubs.append(((cx, cy), (x, y), layer, p['net']))
    return x, y, via, layer


wiring = []
done = failed = 0
fail_list = []
smd = [p for p in pads if p['net'] in plane_nets and p['kind'] == 'smd']
# big pads first (exposed pads), then the crowded fine-pitch pads
smd.sort(key=lambda p: (-(p['w'] * p['h']), p['w'] * p['h']))
for p in smd:
    focus(p['x'], p['y'])
    um = lambda v: '%.1f' % (v * 1000)
    res = place_outside(p)
    if res is None and p['w'] * p['h'] >= 4.0:
        # no room around it (exposed pad): vias inside the pad
        vs = place_inside(p)
        for x, y, via in vs:
            wiring.append('    (via "%s" %s %s (net %s) (type protect))' % (via[1], um(x), um(-y), p['net']))
        if vs:
            done += 1
            continue
    if res is None:
        failed += 1
        fail_list.append('%s.%s (%s)' % (p['ref'], p['num'], p['net']))
        continue
    x, y, via, layer = res
    wiring.append('    (wire (path %s %s %s %s %s %s) (net %s) (type protect))' % (
        layer, um(STUB_W), um(p['x']), um(-p['y']), um(x), um(-y), p['net']))
    wiring.append('    (via "%s" %s %s (net %s) (type protect))' % (via[1], um(x), um(-y), p['net']))
    done += 1

d = open(dsn_in).read()
w = d.find('(wiring')
assert w >= 0
d = d[:w] + '(wiring\n' + '\n'.join(wiring) + '\n' + d[w + len('(wiring'):].lstrip('\n')
open(dsn_out, 'w').write(d)
print('SMD pads of %s: %d with vias, %d without room' % (','.join(plane_nets), done, failed))
if fail_list:
    print('  no room: ' + ', '.join(fail_list))

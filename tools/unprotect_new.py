#!/usr/bin/env python3
"""Prepare a DSN so that fastroute optimizes only the new wiring.

- drops the small planes (teardrop zones exported by KiCad): they would be
  seen as copper to connect and would pin the tracks; the big pours stay;
- removes (type protect) from the wire segments and vias listed by
  tools/new_items.py (KiCad nm and y), with 2 um tolerance; a segment is new
  when it lies on a new KiCad track. New vias that no wire touches (stitching)
  stay fixed, otherwise the optimizer removes them as dangling tails.

The DSN must already be split (tools/split_dsn_wires.py).

usage: unprotect_new.py split.dsn new_items.json out.dsn"""
import json, math, re, sys

src, items_f, dst = sys.argv[1:4]
t = open(src).read()
items = json.load(open(items_f))
TOL = 2.0  # um


def scope_end(s, i):
    d = 0
    for k in range(i, len(s)):
        d += {'(': 1, ')': -1}.get(s[k], 0)
        if d == 0:
            return k + 1


# 1. small planes out
spans = []
for m in re.finditer(r'\(plane ', t):
    e = scope_end(t, m.start())
    nums = list(map(float, re.findall(r'-?\d+(?:\.\d+)?', t[m.start():e].split('(polygon', 1)[1])[2:]))
    xs, ys = nums[0::2], nums[1::2]
    if max(xs) - min(xs) < 15000 and max(ys) - min(ys) < 15000:
        spans.append((m.start(), e))
for s, e in reversed(spans):
    t = t[:t.rfind('\n', 0, s)] + t[e:]
print('small planes removed:', len(spans))

# 2. unprotect the new segments and vias
def um(p):  # KiCad nm -> DSN um (y negated)
    return (p[0] / 1000.0, -p[1] / 1000.0)


new_segs = {}
new_vias = {}
for o in items:
    if o['kind'] == 'track':
        new_segs.setdefault((o['net'], o['layer']), []).append((um(o['a']), um(o['b'])))
    else:
        new_vias.setdefault(o['net'], []).append(um((o['x'], o['y'])))


def close(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= TOL


def on_seg(p, x, y):
    dx, dy = y[0] - x[0], y[1] - x[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return close(p, x)
    u = max(0.0, min(1.0, ((p[0] - x[0]) * dx + (p[1] - x[1]) * dy) / L2))
    return close(p, (x[0] + u * dx, x[1] + u * dy))


def nn(s):
    return s.strip('"')


wire_ends = {}
n_w = 0


def wire(m):
    global n_w
    layer, net = m.group(1), nn(m.group(4))
    p = list(map(float, m.group(3).split()))
    a, b = (p[0], p[1]), (p[2], p[3])
    wire_ends.setdefault(net, []).extend([a, b])
    for x, y in new_segs.get((net, layer), []):
        if on_seg(a, x, y) and on_seg(b, x, y):
            n_w += 1
            return m.group(0).replace('(type protect)', '')
    return m.group(0)


t = re.sub(r'\(wire \(path (\S+) (\S+)\s+([-\d.\s]+?)\)\(net ("[^"]*"|[^)\s]+)\)\s*\(type protect\)\)', wire, t)
n_v = n_fix = 0


def via(m):
    global n_v, n_fix
    net = nn(m.group(3))
    p = (float(m.group(1)), float(m.group(2)))
    if any(close(p, q) for q in new_vias.get(net, [])):
        if any(close(p, q) for q in wire_ends.get(net, [])):
            n_v += 1
            return m.group(0).replace('(type protect)', '')
        n_fix += 1
    return m.group(0)


t = re.sub(r'\(via "[^"]*"\s+([-\d.]+) ([-\d.]+) \(net ("[^"]*"|[^)\s]+)\)\s*\(type protect\)\)', via, t)
open(dst, 'w').write(t)
print('unprotected: %d DSN segments (from %d new KiCad tracks), %d of %d new vias (%d new vias without wires kept fixed)'
      % (n_w, sum(len(v) for v in new_segs.values()), n_v, sum(len(v) for v in new_vias.values()), n_fix))

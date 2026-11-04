#!/usr/bin/env python3
"""Split the wires of a Specctra DSN so that every junction is a wire end.

fastroute, like Freerouting, connects traces only at their ends, while KiCad
connects any copper that touches. Two cases of KiCad 5 exports look broken
to fastroute and get routed again:

- consecutive segments are exported as one multi-point path, and a track
  branching off at an intermediate vertex touches that path in the middle:
  every path becomes 2-point wires;
- a via, or the end of another wire, lying on the middle of a segment of the
  same net (and layer): the segment is split at the projection of that point,
  which is inside the copper of the via / trace end, so fastroute joins it.

usage: split_dsn_wires.py in.dsn out.dsn
"""
import collections
import math
import re
import sys

src, dst = sys.argv[1:3]
t = open(src).read()

WIRE = re.compile(r'\(wire \(path (\S+) (\S+)\s+([-\d.\s]+?)\)(\(net ("[^"]*"|[^)\s]+)\)\s*\(type \w+\)\))')
VIA = re.compile(r'\(via "([^"]*)"\s+([-\d.]+) ([-\d.]+) \(net ("[^"]*"|[^)\s]+)\)')

# pass 1: every path -> 2-point segments
segs = []          # (layer, width, a, b, rest, net)
n_paths = 0
for m in WIRE.finditer(t):
    p = [float(x) for x in m.group(3).split()]
    pts = [(p[i], p[i + 1]) for i in range(0, len(p), 2)]
    n_paths += 1
    for a, b in zip(pts, pts[1:]):
        segs.append((m.group(1), m.group(2), a, b, m.group(4), m.group(5).strip('"')))
if len(WIRE.findall(t)) != len(re.findall(r'\(wire \(path', t)):
    sys.exit('some wires not recognised')

# junction points per net: vias (any layer) and segment ends (per layer)
vias = collections.defaultdict(list)
w = t.find('(wiring')
for m in VIA.finditer(t, w):
    d = re.search(r'_(\d+):', m.group(1))
    r = float(d.group(1)) / 2 if d else 300.0
    vias[m.group(4).strip('"')].append((float(m.group(2)), float(m.group(3)), r))
ends = collections.defaultdict(list)
for layer, width, a, b, rest, net in segs:
    ends[(net, layer)].append((a, float(width) / 2))
    ends[(net, layer)].append((b, float(width) / 2))


def project(a, b, q):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return None
    u = ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2
    if u <= 0 or u >= 1:
        return None
    px, py = a[0] + u * dx, a[1] + u * dy
    return u, (round(px, 1), round(py, 1)), math.hypot(q[0] - px, q[1] - py)


out = []
n_tsplit = 0
for layer, width, a, b, rest, net in segs:
    # as KiCad: the via centre / the other wire's end must be inside the copper
    # of this segment
    hw = float(width) / 2
    cuts = {}
    for x, y, r in vias[net]:
        pr = project(a, b, (x, y))
        if pr and pr[2] <= hw:
            cuts[pr[1]] = pr[0]
    for q, _ in ends[(net, layer)]:
        if q == a or q == b:
            continue
        pr = project(a, b, q)
        if pr and pr[2] <= hw:
            cuts[pr[1]] = pr[0]
    pts = [a] + [c for c, u in sorted(cuts.items(), key=lambda kv: kv[1])
                 if math.hypot(c[0] - a[0], c[1] - a[1]) > 1 and math.hypot(c[0] - b[0], c[1] - b[1]) > 1] + [b]
    n_tsplit += len(pts) - 2
    for p, q in zip(pts, pts[1:]):
        out.append('(wire (path %s %s  %g %g  %g %g)%s' % (layer, width, p[0], p[1], q[0], q[1], rest))

# rebuild the wiring: drop the old wires, write the segments where the first was
spans = [(m.start(), m.end()) for m in WIRE.finditer(t)]
first = spans[0][0]
for s, e in reversed(spans):
    if s == first:
        t = t[:s] + '\x00' + t[e:]
    else:
        # remove the wire and the line break / indentation before it
        t = t[:t.rfind('\n', 0, s)] + t[e:]
t = t.replace('\x00', '\n    '.join(out), 1)
open(dst, 'w').write(t)
print('%d wires -> %d segments (%d extra splits at junctions in the middle of a segment)'
      % (n_paths, len(out), n_tsplit))

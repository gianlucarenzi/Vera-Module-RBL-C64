#!/usr/bin/env python3
"""Remove length-tuning meanders from KiCad 5 tracks of selected nets.

A meander is a stretch of a track that leaves its straight line and comes
back to the same line further on. Each such stretch is replaced by one
straight segment; the rest of the routing is left untouched.

usage: unmeander.py in.kicad_pcb out.kicad_pcb [net-regex]
"""
import math
import re
import sys
from collections import defaultdict

SEG_RE = re.compile(r'^\s*\(segment \(start ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\) '
                    r'\(width ([\d.]+)\) \(layer ([^)]+)\) \(net (\d+)\)(.*)\)\s*$')
TINY = 0.12     # mm: segments shorter than this are pieces of an arc
ONLINE = 0.005  # mm: distance tolerance to call a point "on the baseline"

src, dst = sys.argv[1], sys.argv[2]
pat = re.compile(sys.argv[3] if len(sys.argv) > 3 else r'^m[AD]\d+$')

lines = open(src).read().split('\n')
nets = {}
for l in lines:
    m = re.match(r'^\s*\(net (\d+) "?([^")]*)"?\)\s*$', l)
    if m:
        nets[m.group(1)] = m.group(2)

# collect segments of the target nets, by (net, layer, width)
groups = defaultdict(list)
drop = set()
for i, l in enumerate(lines):
    m = SEG_RE.match(l)
    if m and pat.match(nets.get(m.group(7), '')) and not m.group(8).strip():
        x1, y1, x2, y2 = m.group(1, 2, 3, 4)
        groups[(m.group(7), m.group(6), m.group(5))].append(((x1, y1), (x2, y2), i))


def P(k):
    return (float(k[0]), float(k[1]))


def chains(segs):
    """Split segments into polylines between nodes of degree != 2."""
    adj = defaultdict(list)
    for s in segs:
        if s[0] != s[1]:
            adj[s[0]].append(s)
            adj[s[1]].append(s)
    used = set()
    out = []
    starts = [n for n in adj if len(adj[n]) != 2] + list(adj)
    for n0 in starts:
        for s in adj[n0]:
            if s[2] in used:
                continue
            pts, idx, n = [n0], [], n0
            while True:
                used.add(s[2])
                idx.append(s[2])
                n = s[1] if s[0] == n else s[0]
                pts.append(n)
                nxt = [t for t in adj[n] if t[2] not in used]
                if len(adj[n]) != 2 or not nxt:
                    break
                s = nxt[0]
            out.append((pts, idx))
    return out


def online(p, a, d):
    v = (p[0] - a[0], p[1] - a[1])
    return abs(v[0] * d[1] - v[1] * d[0]) < ONLINE and v[0] * d[0] + v[1] * d[1] > 0


def straighten(xy, keep, st):
    """One pass along the polyline xy[keep]: cut the excursions that leave
    the line of a long segment and come back onto it."""
    q = [xy[k] for k in keep]
    n = len(q) - 1
    seglen = [math.dist(q[i], q[i + 1]) for i in range(n)]
    out = [keep[0]]
    i = 1
    while i < n:
        if seglen[i] < TINY and seglen[i - 1] >= TINY:
            a, b = q[i - 1], q[i]
            d = ((b[0] - a[0]) / seglen[i - 1], (b[1] - a[1]) / seglen[i - 1])
            j = max((k for k in range(i + 1, n + 1) if online(q[k], b, d)), default=None)
            if j is not None and any(seglen[k] < TINY for k in range(i, j)):
                st[0] += 1
                st[1] += sum(seglen[i - 1:j]) - math.dist(a, q[j])
                i = j
                continue
        out.append(keep[i])
        i += 1
    out.append(keep[n])
    return out


new = defaultdict(list)  # insert-after line index -> new segment lines
stats = defaultdict(lambda: [0, 0.0, 0.0])
for (net, layer, width), segs in groups.items():
    for pts, idx in chains(segs):
        xy = [P(k) for k in pts]
        n = len(xy) - 1
        seglen = [math.dist(xy[i], xy[i + 1]) for i in range(n)]
        if not any(l < TINY for l in seglen):
            continue
        keep = list(range(n + 1))  # indices of points that survive
        for _ in range(6):
            before = len(keep)
            keep = straighten(xy, keep, stats[nets[net]])
            keep = straighten(xy, keep[::-1], stats[nets[net]])[::-1]
            if len(keep) == before:
                break
        if len(keep) == n + 1:
            continue
        for k in idx:
            drop.add(k)
        for u, v in zip(keep, keep[1:]):
            s = '  (segment (start %s %s) (end %s %s) (width %s) (layer %s) (net %s))' % (
                pts[u][0], pts[u][1], pts[v][0], pts[v][1], width, layer, net)
            new[idx[0]].append(s)

out = []
for i, l in enumerate(lines):
    if i not in drop:
        out.append(l)
    out.extend(new.get(i, []))
open(dst, 'w').write('\n'.join(out))

for name in sorted(stats):
    c, removed, _ = stats[name]
    print('%-6s meanders removed: %2d  length removed: %7.2f mm' % (name, c, removed))
print('segments: %d dropped, %d added' % (len(drop), sum(len(v) for v in new.values())))

#!/usr/bin/env python3
"""List the tracks and vias of NEW.kicad_pcb that are not in OLD.kicad_pcb.

A track is old when it lies on a track of OLD with the same net and layer
(2 um tolerance: a Specctra session import rounds the coordinates and splits
the tracks at the junctions); a via is old when OLD has a via of the same net
at the same place. Read-only (pcbnew module, nothing is saved).

usage: new_items.py OLD.kicad_pcb NEW.kicad_pcb OUT.json"""
import json, math, sys, collections
import pcbnew

TOL = pcbnew.FromMM(0.002)
A = pcbnew.LoadBoard(sys.argv[1]); B = pcbnew.LoadBoard(sys.argv[2])
mm = pcbnew.ToMM

old_seg = collections.defaultdict(list)
old_via = collections.defaultdict(list)
for t in A.GetTracks():
    if t.GetClass() == 'VIA':
        old_via[t.GetNetname()].append((t.GetPosition().x, t.GetPosition().y))
    else:
        old_seg[(t.GetNetname(), A.GetLayerName(t.GetLayer()))].append(
            (t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y))


def on_seg(p, s):
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(p[0] - x1, p[1] - y1) <= TOL
    u = ((p[0] - x1) * dx + (p[1] - y1) * dy) / L2
    u = max(0.0, min(1.0, u))
    return math.hypot(p[0] - (x1 + u * dx), p[1] - (y1 + u * dy)) <= TOL


out = []
stats = collections.Counter()
length = 0.0
for t in B.GetTracks():
    net = t.GetNetname()
    if t.GetClass() == 'VIA':
        p = (t.GetPosition().x, t.GetPosition().y)
        if any(math.hypot(p[0] - q[0], p[1] - q[1]) <= TOL for q in old_via[net]):
            stats['old via'] += 1
            continue
        stats['new via'] += 1
        out.append({'kind': 'via', 'net': net, 'x': p[0], 'y': p[1]})
    else:
        L = B.GetLayerName(t.GetLayer())
        a = (t.GetStart().x, t.GetStart().y); b = (t.GetEnd().x, t.GetEnd().y)
        segs = old_seg[(net, L)]
        if any(on_seg(a, s) and on_seg(b, s) for s in segs):
            stats['old track'] += 1
            continue
        stats['new track'] += 1
        length += mm(t.GetLength())
        out.append({'kind': 'track', 'net': net, 'layer': L, 'a': a, 'b': b, 'w': t.GetWidth()})
json.dump(out, open(sys.argv[3], 'w'))
print(dict(stats), 'new track length %.1f mm' % length)
print('nets:', dict(sorted(collections.Counter(o['net'] for o in out).items())))

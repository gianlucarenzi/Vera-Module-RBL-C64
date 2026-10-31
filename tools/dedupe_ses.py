#!/usr/bin/env python3
"""Drop duplicated vias and wires from a Specctra session.

A via is a duplicate when another via of the same net sits at the same
point; a wire is a duplicate when every one of its segments lies on another
wire of the same net and layer.

usage: dedupe_ses.py in.ses out.ses
"""
import re
import sys

src, dst = sys.argv[1:3]
t = open(src).read()


def scope_end(s, i):
    d = 0
    for k in range(i, len(s)):
        d += {'(': 1, ')': -1}.get(s[k], 0)
        if d == 0:
            return k + 1


def on_seg(p, a, b, tol=2):
    # p on segment a-b, in session units (0.1 um)
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    l = max(abs(b[0] - a[0]), abs(b[1] - a[1]), 1)
    if abs(cross) / l > tol:
        return False
    return (min(a[0], b[0]) - tol <= p[0] <= max(a[0], b[0]) + tol and
            min(a[1], b[1]) - tol <= p[1] <= max(a[1], b[1]) + tol)


out, pos, vias_rm, wires_rm = [], 0, 0, 0
for m in re.finditer(r'\(net "?([^"\n]*?)"?\n', t):
    i = m.start()
    j = scope_end(t, i)
    body = t[i:j]
    items = []
    k = 0
    while True:
        a = body.find('(wire', k)
        b = body.find('(via', k)
        starts = [x for x in (a, b) if x >= 0]
        if not starts:
            break
        s = min(starts)
        e = scope_end(body, s)
        items.append((s, e, body[s:e]))
        k = e
    if not items:
        continue
    vias, wires = [], []
    for s, e, txt in items:
        if txt.startswith('(via'):
            xy = tuple(int(float(v)) for v in re.match(r'\(via "?[^" ]+"? ([-\d.]+) ([-\d.]+)', txt).groups())
            vias.append((s, e, xy))
        else:
            pm = re.search(r'\(path (\S+) ([\d.]+)\s+([-\d.\s]+)\)', txt)
            nums = [int(float(v)) for v in pm.group(3).split()]
            pts = list(zip(nums[::2], nums[1::2]))
            wires.append((s, e, pm.group(1), pts))
    drop = set()
    seen = set()
    for s, e, xy in vias:
        if xy in seen:
            drop.add(s)
        seen.add(xy)
    for wi, (s, e, layer, pts) in enumerate(wires):
        segs = list(zip(pts, pts[1:]))
        for wj, (s2, e2, layer2, pts2) in enumerate(wires):
            if wj == wi or layer2 != layer or s2 in drop:
                continue
            others = list(zip(pts2, pts2[1:]))
            # covered: both ends of every segment on one segment of the other wire
            if all(any(on_seg(a, c, d) and on_seg(b, c, d) for c, d in others) for a, b in segs):
                drop.add(s)
                break
    if not drop:
        continue
    vias_rm += sum(1 for s, _, _ in vias if s in drop)
    wires_rm += sum(1 for s, _, _, _ in wires if s in drop)
    nb = body
    for s, e, _ in sorted(items, reverse=True):
        if s in drop:
            # remove the item and the whitespace before it
            ls = nb.rfind('\n', 0, s)
            nb = nb[:ls] + nb[e:]
    out.append((i, j, nb))

for i, j, nb in reversed(out):
    t = t[:i] + nb + t[j:]
open(dst, 'w').write(t)
print('removed %d duplicate vias, %d duplicate wires' % (vias_rm, wires_rm))

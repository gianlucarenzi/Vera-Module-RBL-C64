#!/usr/bin/env python3
"""List the nets of a KiCad 5 board whose pads are not all connected.

Read-only (pcbnew module, the board is never saved). Pads, tracks, vias and
the FILLED area of the zones are joined per net; a net with more than one
group of pads has missing connections. Fill the zones (B) and save before.

usage: unrouted_nets.py board.kicad_pcb [-v]
  prints the nets comma-separated (for tools/filter_ses.py); -v also prints
  the groups of pads of each net on stderr. The per-net check is geometric
  (pad centre and thermal spoke points against the fill): KiCad's total from
  its ratsnest is printed too, and when it is 0 no net is printed.
"""
import collections
import sys

import pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
verbose = '-v' in sys.argv

by_net = collections.defaultdict(lambda: ([], [], []))
for m in b.GetModules():
    for p in m.Pads():
        if p.GetNetCode():
            by_net[p.GetNetname()][0].append(p)
for t in b.GetTracks():
    if t.GetNetCode():
        by_net[t.GetNetname()][1].append(t)
for i in range(b.GetAreaCount()):
    z = b.GetArea(i)
    if z.GetNetCode() and not z.GetIsKeepout():
        by_net[z.GetNetname()][2].append(z)


def points(x):
    if isinstance(x, pcbnew.D_PAD) or x.GetClass() == 'VIA':
        return [x.GetPosition()]
    return [x.GetStart(), x.GetEnd()]


def zone_points(x):
    """points to test against a zone fill: for a pad also the middle of each
    side pushed out past the thermal gap, where the thermal spokes are (the
    pad centre sits in the hole that the fill leaves around the pad)"""
    if not isinstance(x, pcbnew.D_PAD):
        return points(x)
    c = x.GetPosition()
    bb = x.GetBoundingBox()
    out = pcbnew.FromMM(0.7)
    return [c,
            pcbnew.wxPoint(bb.GetLeft() - out, c.y), pcbnew.wxPoint(bb.GetRight() + out, c.y),
            pcbnew.wxPoint(c.x, bb.GetTop() - out), pcbnew.wxPoint(c.x, bb.GetBottom() + out)]


def share_layer(a, c):
    return any(c.IsOnLayer(layer) for layer in a.GetLayerSet().CuStack())


nets = []
total = 0
for net, (P, T, Z) in sorted(by_net.items()):
    if len(P) < 2:
        continue
    items = P + T
    par = list(range(len(items) + len(Z)))

    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    for i, a in enumerate(items):
        for j in range(i + 1, len(items)):
            c = items[j]
            if not share_layer(a, c):
                continue
            if any(c.HitTest(q) for q in points(a)) or any(a.HitTest(q) for q in points(c)):
                par[f(i)] = f(j)
        for k, z in enumerate(Z):
            if a.IsOnLayer(z.GetLayer()) and any(z.HitTestFilledArea(q) for q in zone_points(a)):
                par[f(i)] = f(len(items) + k)
    groups = collections.defaultdict(list)
    for i, a in enumerate(P):
        groups[f(i)].append(a.GetParent().GetReference() + '-' + a.GetName())
    if len(groups) > 1:
        nets.append(net)
        total += len(groups) - 1
        if verbose:
            sys.stderr.write('%-20s %s\n' % (net, ' | '.join(','.join(sorted(g)) for g in groups.values())))
sys.stderr.write('%d nets, %d missing connections\n' % (len(nets), total))

# KiCad's own count is the reference (the per-net ratsnest is not reachable
# from Python in KiCad 5.1): the geometric check above can miss a thermal
# spoke or a track crossing a pad off its centre
b.BuildConnectivity()
conn = b.GetConnectivity()
conn.RecalculateRatsnest()
kicad = conn.GetUnconnectedCount()
sys.stderr.write('KiCad ratsnest: %d missing connections\n' % kicad)
if kicad == 0:
    nets = []
elif kicad != total:
    sys.stderr.write('WARNING: the per-net list may be incomplete or include false positives\n')
print(','.join(nets))

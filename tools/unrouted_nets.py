#!/usr/bin/env python3
"""List the nets of a KiCad 5 board whose pads are not all connected.

Read-only (pcbnew module, the board is never saved). Pads, tracks, vias and
the FILLED area of the zones are joined per net; a net with more than one
group of pads has missing connections. Fill the zones (B) and save before.

usage: unrouted_nets.py board.kicad_pcb [-v]
  prints the nets comma-separated (for tools/filter_ses.py); -v also prints
  the groups of pads of each net on stderr
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
            if a.IsOnLayer(z.GetLayer()) and any(z.HitTestFilledArea(q) for q in points(a)):
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
print(','.join(nets))

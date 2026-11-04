#!/usr/bin/env python3
"""Clean a fastroute session of an incremental run (existing wiring fixed).

KiCad 5 replaces ALL tracks and vias with the session content on import, so
the session must hold the existing wiring exactly once and unchanged:

- every fixed (type protect) wire segment and via of the DSN is kept exactly
  once, with its DSN width (fastroute may write fixed wires again, several
  times, or narrowed at the pins);
- protected items that are not in the DSN (the short joins fastroute adds at
  load time from a trace end to the pad centre) are dropped;
- new (unprotected) wiring is kept only on the given nets, i.e. the nets that
  really had missing connections (tools/unrouted_nets.py).

The DSN must be the one given to fastroute (after tools/split_dsn_wires.py).

usage: filter_ses.py board.dsn in.ses out.ses NET1,NET2,...
"""
import collections
import re
import sys

dsn = open(sys.argv[1]).read()
ses = open(sys.argv[2]).read()
OUT = sys.argv[3]
TARGET = set(sys.argv[4].split(','))
K = 10  # DSN coordinates in um, session in 0.1 um


def nn(s):
    return s.strip('"')


def seg_key(net, layer, a, b):
    return (net, layer) + tuple(sorted([a, b]))


def scope_end(s, i):
    d = 0
    for k in range(i, len(s)):
        d += {'(': 1, ')': -1}.get(s[k], 0)
        if d == 0:
            return k + 1


D = collections.Counter()
WD = collections.defaultdict(list)
for m in re.finditer(r'\(wire \(path (\S+) (\S+)\s+([-\d.\s]+?)\)\(net ("[^"]*"|[^)\s]+)\)\s*\(type protect\)', dsn):
    p = list(map(float, m.group(3).split()))
    pts = [(round(p[q] * K), round(p[q + 1] * K)) for q in range(0, len(p), 2)]
    for a, b in zip(pts, pts[1:]):
        key = seg_key(nn(m.group(4)), m.group(1), a, b)
        D[key] += 1
        WD[key].append(round(float(m.group(2)) * K))
VD = collections.Counter((nn(m.group(3)), round(float(m.group(1)) * K), round(float(m.group(2)) * K))
                         for m in re.finditer(r'\(via "[^"]*"\s+([-\d.]+) ([-\d.]+) \(net ("[^"]*"|[^)\s]+)\)\s*\(type protect\)', dsn))

used = collections.Counter()
usedv = collections.Counter()
stats = collections.Counter()
out = []
pos = 0
for nm in re.finditer(r'\(net ("[^"]*"|[^\s()]+)\s*\n\s*\((?:wire|via)', ses):
    net = nn(nm.group(1))
    i = nm.start()
    e = scope_end(ses, i)
    body = ses[i:e]
    head = body[:body.index('\n')]
    items = []
    j = len(head)
    while True:
        m = re.search(r'\((wire|via)', body[j:])
        if not m:
            break
        s = j + m.start()
        t = scope_end(body, s)
        items.append(body[s:t])
        j = t
    keep = []
    for it in items:
        prot = '(type protect)' in it
        if it.startswith('(wire'):
            w = re.search(r'\(path (\S+) (\S+)\s+([-\d\s]+)\)', it)
            p = list(map(int, w.group(3).split()))
            pts = [(p[q], p[q + 1]) for q in range(0, len(p), 2)]
            if prot:
                for a, b in zip(pts, pts[1:]):
                    key = seg_key(net, w.group(1), a, b)
                    if used[key] < D.get(key, 0):
                        width = WD[key][used[key]]
                        used[key] += 1
                        keep.append('(wire\n          (path %s %d\n            %d %d\n            %d %d\n'
                                    '          )\n          (type protect)\n        )'
                                    % (w.group(1), width, a[0], a[1], b[0], b[1]))
                        stats['fixed segments'] += 1
                    else:
                        stats['fixed duplicates / load joins dropped'] += 1
            elif net in TARGET:
                keep.append(it)
                stats['new wires kept'] += 1
            else:
                stats['new wires dropped (complete nets)'] += 1
        else:
            v = re.search(r'\(via "[^"]*" (-?\d+) (-?\d+)', it)
            key = (net, int(v.group(1)), int(v.group(2)))
            if prot:
                if usedv[key] < VD.get(key, 0):
                    usedv[key] += 1
                    keep.append(it)
                    stats['fixed vias'] += 1
                else:
                    stats['fixed via duplicates dropped'] += 1
            elif net in TARGET:
                keep.append(it)
                stats['new vias kept'] += 1
            else:
                stats['new vias dropped (complete nets)'] += 1
    out.append(ses[pos:i])
    out.append(head + ''.join('\n        ' + x for x in keep) + '\n      )')
    pos = e
out.append(ses[pos:])
open(OUT, 'w').write(''.join(out))

miss = sum(D[k] - used[k] for k in D if used[k] < D[k] and k[2] != k[3])
zero = sum(D[k] - used[k] for k in D if used[k] < D[k] and k[2] == k[3])
missv = sum(VD[k] - usedv[k] for k in VD if usedv[k] < VD[k])
for k, v in sorted(stats.items()):
    print('  %-40s %d' % (k, v))
print('fixed segments missing: %d (plus %d of zero length), fixed vias missing: %d' % (miss, zero, missv))
if miss or missv:
    sys.exit('the session lacks existing wiring: do NOT import it')

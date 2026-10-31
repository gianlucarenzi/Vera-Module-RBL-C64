#!/usr/bin/env python3
"""Prepare a KiCad 5 Specctra DSN for fastroute.

- the inner layers GND and POWER become pure planes (no tracks): a mixed
  layer gets cut into islands by the signals, and fastroute does not see it;
- the GND pours of F.Cu and B.Cu are dropped, so the router does not count
  on them: every GND/3V3 pad gets its own via (tools/plane_vias.py);
- with --clear, every wire and via of the (wiring ...) scope is dropped, to
  route from scratch.

usage: prep_dsn.py in.dsn out.dsn [--clear]
"""
import re
import sys

PLANE_LAYERS = ('GND', 'POWER')
OUTER_POURS = [('GND', 'F.Cu'), ('GND', 'B.Cu')]

src, dst = sys.argv[1], sys.argv[2]
t = open(src).read()


def scope_end(s, i):
    d = 0
    for k in range(i, len(s)):
        d += {'(': 1, ')': -1}.get(s[k], 0)
        if d == 0:
            return k + 1


for layer in PLANE_LAYERS:
    t, n = re.subn(r'(\(layer %s\s*\(type )signal\)' % re.escape(layer), r'\1power)', t)
    assert n == 1, 'layer %s not found as a signal layer' % layer

removed = 0
for net, layer in OUTER_POURS:
    i = t.find('(plane %s (polygon %s ' % (net, layer))
    if i >= 0:
        t = t[:i] + t[scope_end(t, i):]
        removed += 1

if '--clear' in sys.argv:
    w = t.find('(wiring')
    t = t[:w] + '(wiring\n  )' + t[scope_end(t, w):]
    print('wiring cleared')

open(dst, 'w').write(t)
print('%s -> power planes, %d outer pours removed' % (', '.join(PLANE_LAYERS), removed))

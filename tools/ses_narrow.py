#!/usr/bin/env python3
"""List the wires of a Specctra session narrower than a minimum width.

fastroute leaves short slivers at pad entries even with
--router.min_trace_width_um; KiCad's DRC flags them as too small. A sliver
lying wholly inside its pad can be deleted, one on the way to the pad has
to be widened or rerouted by hand.

usage: ses_narrow.py in.ses [min_width_mm]   (default 0.2)
"""
import re
import sys

src = sys.argv[1]
min_w = float(sys.argv[2]) if len(sys.argv) > 2 else 0.2
t = open(src).read()
res = re.search(r'\(resolution (\w+) (\d+)\)', t)
# session coordinates are in 1/N of the unit
scale = {'um': 1e-3, 'mm': 1.0, 'mil': 0.0254}[res.group(1)] / int(res.group(2))

found = 0
for m in re.finditer(r'\(net "?([^"\n]*?)"?\n(.*?)\n      \)', t, re.S):
    for p in re.finditer(r'\(path (\S+) ([\d.]+)\s+([-\d.\s]+)\)', m.group(2)):
        w = float(p.group(2)) * scale
        if w < min_w:
            v = [float(x) * scale for x in p.group(3).split()]
            # KiCad y is the negated Specctra y
            pts = ' '.join('(%.3f, %.3f)' % (x, -y) for x, y in zip(v[::2], v[1::2]))
            print('%-20s %-6s %.3f mm  %s' % (m.group(1), p.group(1), w, pts))
            found += 1
print('%d wires narrower than %.3f mm' % (found, min_w))

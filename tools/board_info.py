#!/usr/bin/env python3
"""Board facts for the fastroute scripts, as shell assignments.

Finds the only .kicad_pcb in PROJECT_DIR and reads its copper layers, so the
same tools/ work on every KiCad 5 board:

  BOARD=<name without .kicad_pcb>
  INNER=<inner copper layers, comma separated, top to bottom>
  COSTS=<per-layer trace costs for fastroute: 1 outer, INNER_COST inner>

usage: eval "$(python3 tools/board_info.py PROJECT_DIR [INNER_COST])"
"""
import glob
import os
import re
import sys

proj = sys.argv[1]
cost = sys.argv[2] if len(sys.argv) > 2 else '25'
boards = sorted(glob.glob(os.path.join(proj, '*.kicad_pcb')))
if len(boards) != 1:
    sys.exit('expected one .kicad_pcb in %s, found %d' % (proj, len(boards)))
t = open(boards[0]).read()
layers = re.search(r'\n  \(layers\n(.*?)\n  \)', t, re.S).group(1)
# KiCad 5: copper layers are numbered 0 (F.Cu) to 31 (B.Cu), in stack order
copper = [name for num, name in re.findall(r'\((\d+) (\S+) (?:signal|power|mixed|jumper)\)', layers)
          if int(num) <= 31]
inner = [c for c in copper if c not in ('F.Cu', 'B.Cu')]
print('BOARD=%s' % os.path.basename(boards[0])[:-len('.kicad_pcb')])
print('INNER=%s' % ','.join(inner))
print('COSTS=%s' % ','.join(['1'] + [cost] * len(inner) + ['1']))

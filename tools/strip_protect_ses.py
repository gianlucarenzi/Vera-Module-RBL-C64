#!/usr/bin/env python3
"""Drop the protected wires and vias from a Specctra session.

fastroute writes the pre-placed plane vias (type protect) into the session
too. When that session is the --initial-session of a run whose DSN already
holds the same vias, they would be loaded twice; without them in the DSN the
router would be free to rip them up. So keep them in the DSN and strip them
from the session with this script.

usage: strip_protect_ses.py in.ses out.ses
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


spans = []
for m in re.finditer(r'\((wire|via)\b', t):
    e = scope_end(t, m.start())
    if '(type protect)' in t[m.start():e]:
        spans.append((m.start(), e))
for s, e in reversed(spans):
    # remove the item and the whitespace before it
    t = t[:t.rfind('\n', 0, s)] + t[e:]
open(dst, 'w').write(t)
print('removed %d protected wires/vias' % len(spans))

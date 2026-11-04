#!/usr/bin/env python3
"""Split every multi-point wire of a Specctra DSN into 2-point wires.

KiCad 5 exports consecutive track segments as one multi-point path, so a
track that branches off at an intermediate vertex (a T junction) touches the
other path in the middle. fastroute, like Freerouting, connects traces only
at their ends: it sees those nets as broken and routes them again. With one
wire per segment every vertex is a wire end and the junctions connect.

usage: split_dsn_wires.py in.dsn out.dsn
"""
import re
import sys

src, dst = sys.argv[1:3]
t = open(src).read()
n_in = n_out = 0


def split(m):
    global n_in, n_out
    layer, width, rest = m.group(1), m.group(2), m.group(4)
    p = m.group(3).split()
    pts = [(p[i], p[i + 1]) for i in range(0, len(p), 2)]
    n_in += 1
    out = []
    for a, b in zip(pts, pts[1:]):
        out.append('(wire (path %s %s  %s %s  %s %s)%s' % (layer, width, a[0], a[1], b[0], b[1], rest))
        n_out += 1
    return '\n    '.join(out)


t = re.sub(r'\(wire \(path (\S+) (\S+)\s+([-\d.\s]+?)\)(\(net (?:"[^"]*"|[^)\s]+)\)\(type \w+\)\))', split, t)
left = len(re.findall(r'\(wire \(path', t)) - n_out
if left:
    sys.exit('%d wires not recognised' % left)
open(dst, 'w').write(t)
print('%d wires -> %d segments' % (n_in, n_out))

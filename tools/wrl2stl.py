#!/usr/bin/env python3
# VRML 2.0 (nested Transform / Shape / IndexedFaceSet, DEF/USE) -> one binary
# STL per diffuse colour, in the file's world units (mm with the top scale of
# a KiCad export), plus parts.json (file, rgb, triangles, bounding box).
# Used by tools/fc_assembly.sh for the C64 motherboard; needs numpy.
# Usage: tools/wrl2stl.py IN.wrl OUTDIR
import json
import math
import os
import re
import struct
import sys

import numpy as np

src = open(sys.argv[1]).read()
out = sys.argv[2]
os.makedirs(out, exist_ok=True)
TOK = re.compile(r'\s*(#[^\n]*|\[|\]|\{|\}|[^\s\[\]\{\},]+|,)')


class P:
    def __init__(self, s):
        self.s, self.i = s, 0

    def tok(self):
        while True:
            m = TOK.match(self.s, self.i)
            if not m:
                return None
            self.i = m.end()
            t = m.group(1)
            if t.startswith("#") or t == ",":
                continue
            return t

    def peek(self):
        j = self.i
        t = self.tok()
        self.i = j
        return t

    def array(self):
        # after '[': numbers up to ']'
        j = self.s.index("]", self.i)
        a = np.array(self.s[self.i:j].replace(",", " ").split(), dtype=float)
        self.i = j + 1
        return a


defs = {}
groups = {}          # colour -> list of triangle arrays


def rot(axis, ang):
    x, y, z = axis / (np.linalg.norm(axis) or 1)
    c, s, C = math.cos(ang), math.sin(ang), 1 - math.cos(ang)
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def node(p, M):
    """parse a node (after its type name), return a value"""
    t = p.tok()
    name = None
    if t == "DEF":
        name = p.tok()
        t = p.tok()
    if t == "USE":
        return defs[p.tok()]
    typ = t
    assert p.tok() == "{", typ
    f = {}
    if typ == "Transform":
        f = dict(center=np.zeros(3), rotation=np.array([0, 0, 1, 0.]), scale=np.ones(3),
                 scaleOrientation=np.array([0, 0, 1, 0.]), translation=np.zeros(3))
    kids_start = None
    while True:
        k = p.tok()
        if k == "}":
            break
        if k == "children":
            # build the matrix now: fields come before children in this file
            if typ == "Transform":
                A = np.eye(4)
                Rm = np.eye(4); Rm[:3, :3] = rot(f["rotation"][:3], f["rotation"][3])
                SR = np.eye(4); SR[:3, :3] = rot(f["scaleOrientation"][:3], f["scaleOrientation"][3])
                S = np.diag(list(f["scale"]) + [1])
                T = np.eye(4); T[:3, 3] = f["translation"]
                Cm = np.eye(4); Cm[:3, 3] = f["center"]
                Ci = np.eye(4); Ci[:3, 3] = -f["center"]
                A = T @ Cm @ Rm @ SR @ S @ np.linalg.inv(SR) @ Ci
                Mk = M @ A
            else:
                Mk = M
            assert p.tok() == "["
            while p.peek() != "]":
                node(p, Mk)
            p.tok()
        elif k in ("appearance", "geometry", "material", "coord", "normal"):
            f[k] = node(p, M)
        elif k in ("point", "coordIndex", "vector", "normalIndex"):
            assert p.tok() == "["
            f[k] = p.array()
        else:
            # scalar / vector fields
            vals = []
            while True:
                q = p.peek()
                if q is None or re.match(r'^[a-zA-Z]', q) and q not in ("TRUE", "FALSE") or q in ("}",):
                    break
                vals.append(p.tok())
            try:
                f[k] = np.array([float(v) for v in vals])
            except ValueError:
                f[k] = vals
    val = (typ, f)
    if typ == "Shape":
        geo = f.get("geometry")
        app = f.get("appearance")
        col = (0.6, 0.6, 0.6)
        if app and "material" in app[1]:
            col = tuple(np.round(app[1]["material"][1].get("diffuseColor", col), 3))
        if geo and geo[0] == "IndexedFaceSet":
            pts = geo[1]["coord"][1]["point"].reshape(-1, 3)
            pts = (M[:3, :3] @ pts.T).T + M[:3, 3]
            idx = geo[1]["coordIndex"].astype(int)
            tris, face = [], []
            for v in idx:
                if v < 0:
                    for a in range(1, len(face) - 1):
                        tris.append((face[0], face[a], face[a + 1]))
                    face = []
                else:
                    face.append(v)
            if tris:
                groups.setdefault(col, []).append(pts[np.array(tris)])
    if name:
        defs[name] = val
    return val


p = P(src)
assert p.s.startswith("#VRML V2.0")
while p.peek() is not None:
    node(p, np.eye(4))

info = []
for k, (col, lst) in enumerate(sorted(groups.items(), key=lambda kv: -sum(len(a) for a in kv[1]))):
    tri = np.concatenate(lst).astype(np.float32)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    fn = "part%02d.stl" % k
    with open(os.path.join(out, fn), "wb") as fh:
        fh.write(b"\0" * 80 + struct.pack("<I", len(tri)))
        rec = np.zeros(len(tri), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
        rec["n"], rec["v"] = n, tri
        fh.write(rec.tobytes())
    lo, hi = tri.reshape(-1, 3).min(0), tri.reshape(-1, 3).max(0)
    info.append(dict(file=fn, rgb=[float(c) for c in col], tris=len(tri), lo=lo.tolist(), hi=hi.tolist()))
json.dump(info, open(os.path.join(out, "parts.json"), "w"), indent=1)
print("wrl2stl: %d meshes, %d triangles" % (len(info), sum(i["tris"] for i in info)))

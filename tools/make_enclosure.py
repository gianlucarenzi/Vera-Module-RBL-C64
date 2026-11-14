#!/usr/bin/env python3
"""Two-shell enclosure for the VERA module (RBL-XE / RBL-C64), with room for
the VERA-HDMI-Expansion stacked on top. Runs in FreeCAD without GUI:

  freecadcmd tools/make_enclosure.py      (settings from the environment)

Environment:
  ENC_DATA    JSON from tools/enclosure_data.py
  ENC_STEP    STEP of this board (images/VERA-MODULE-RBL.step)
  ENC_HDMI    STEP of the VERA-HDMI-Expansion (optional)
  ENC_CUT     KiCad y (mm) where the case ends and the edge connector comes
              out (the root of the card edge fingers)
  ENC_NAME    output name, ENC_OUT output folder

Only the Part module is used (boxes, extrusions, 2D offsets, booleans,
Part.read, exportStep, exportStl), so it runs on FreeCAD 0.19 (Debian 11),
0.20/0.21 (Debian 12 and backports) and 1.0 (Debian 13).

Coordinates: X = KiCad x, Y = -KiCad y, Z = 0 on the bottom face of the PCB.
The shells split at Z = 0: the lower one holds the board on four bosses
under the M3 holes, its outer half wall rises 2 mm as a lip into the upper
one. Every part that crosses the side wall in the STEP (connectors, the
card edge fingers, the HDMI connector of the add-on) gets an opening.
"""
import json
import math
import os

import FreeCAD as App
import Part

V = App.Vector
WALL = 1.5          # wall, floor and roof thickness
GAP = 0.5           # board edge to inner wall
LIP = 2.0           # lip height of the lower shell
CLEAR = 1.0         # tallest part to roof / floor
STANDOFF = 14.0     # M3 F/F standoff between the module and the HDMI board
BOSS_D = 7.0        # boss diameter
SCREW_D = 3.2       # M3 clearance hole
VENT_W, VENT_PITCH, VENT_SIZE = 1.6, 3.6, 24.0
PIN_HOLE = 3.0      # access to RESET and BOOT0

env = os.environ.get
data = json.load(open(env("ENC_DATA")))
name = env("ENC_NAME", "enclosure")
out = env("ENC_OUT", ".")
ycut = float(env("ENC_CUT"))
os.makedirs(out, exist_ok=True)
T = data["thickness"]


def kc(p):
    """KiCad point -> case XY"""
    return V(p[0], -p[1], 0)


def face(points):
    pts = [kc(p) for p in points]
    return Part.Face(Part.makePolygon(pts + [pts[0]]))


def prism(f, z0, z1):
    return f.translated(V(0, 0, z0)).extrude(V(0, 0, z1 - z0))


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def place(shape, outline, dx=0.0, dy=0.0, z=0.0):
    """Move a KiCad STEP so that its board sits on `outline` (KiCad mm)
    shifted by dx, dy, with the bottom of the board at z. The board is the
    solid whose plan matches the outline."""
    xs = [p[0] + dx for p in outline]
    ys = [-(p[1] + dy) for p in outline]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    pcb = None
    for s in shape.Solids:
        b = s.BoundBox
        if abs(b.XLength - w) < 0.3 and abs(b.YLength - h) < 0.3 and b.ZLength < T + 0.5:
            pcb = b
            break
    if pcb is None:
        raise RuntimeError("board solid not found in the STEP")
    return shape.translated(V(min(xs) - pcb.XMin, min(ys) - pcb.YMin, z - pcb.ZMin))


# ---------------------------------------------------------------- the boards
board = place(Part.read(env("ENC_STEP")), data["outline"])
parts = list(board.Solids)
hdmi_top = None
if env("ENC_HDMI") and "hdmi" in data:
    hd = data["hdmi"]
    hdmi = place(Part.read(env("ENC_HDMI")), hd["outline"], 0, 0, T + STANDOFF)
    parts += list(hdmi.Solids)
    hdmi_top = T + STANDOFF + hd["thickness"]
zmax = max(s.BoundBox.ZMax for s in parts)
zmin = min(s.BoundBox.ZMin for s in board.Solids)
z_floor = zmin - CLEAR - WALL          # bottom of the case
z_roof = zmax + CLEAR + WALL           # top of the case

# ---------------------------------------------------------------- plan
pl = face(data["outline"])
bb = pl.BoundBox
clip = Part.makePlane(bb.XLength + 40, bb.YLength + 40, V(bb.XMin - 20, -ycut, 0))
plan = pl.common(clip).Faces[0]                       # board up to the fingers
inner = plan.makeOffset2D(GAP, 0)
mid = plan.makeOffset2D(GAP + WALL / 2, 0)
outer = plan.makeOffset2D(GAP + WALL, 0)


def ring(fa, fb, z0, z1):
    return prism(fb, z0, z1).cut(prism(fa, z0 - 1, z1 + 1))


lower = prism(outer, z_floor, 0).cut(prism(inner, z_floor + WALL, 1))
lower = lower.fuse(ring(mid, outer, 0, LIP))
upper = prism(outer, LIP, z_roof).cut(prism(inner, LIP - 1, z_roof - WALL))
upper = upper.fuse(ring(inner, mid, 0, LIP))

# ---------------------------------------------------------------- openings
openings = []
# Port side (the board edge at the smallest KiCad y): one open window from
# the lowest to the highest part that reaches the wall there (connectors of
# the module and the HDMI connector of the add-on), with a frame of WALL
# left at the sides and at the roof
y_edge = -min(p[1] for p in data["outline"])          # case Y of that edge
# parts within 2 mm of the board edge (recessed jacks included), boards excluded
reach = [s.BoundBox for s in parts if s.BoundBox.YMax > y_edge - 2.0 and s.BoundBox.XLength < 60]
if reach:
    # footprint boxes too: a part without STEP model is missing from `reach`
    pp = data.get("port_parts", {}).values()
    wx0 = min([b.XMin for b in reach] + [p["x0"] for p in pp]) - 1.0
    wx1 = max([b.XMax for b in reach] + [p["x1"] for p in pp]) + 1.0
    wz0 = max(min(b.ZMin for b in reach) - 1.0, z_floor + WALL)
    wz1 = min(max(b.ZMax for b in reach) + 1.0, z_roof - WALL)
    openings.append(box(wx0, wx1, y_edge + GAP - 0.1, y_edge + 20, wz0, wz1))
    print("port window: x %.1f..%.1f (KiCad), z %.1f..%.1f mm" % (wx0, wx1, wz0, wz1))
# Card edge fingers: a slot where the board crosses the wall at ENC_CUT
fingers = pl.cut(clip)
for f in fingers.Faces:
    fb = f.BoundBox
    openings.append(box(fb.XMin - 0.5, fb.XMax + 0.5, -ycut - 20, -ycut + 1, -0.6, T + 0.6))
for o in openings:
    lower = lower.cut(o)
    upper = upper.cut(o)

# ---------------------------------------------------------------- bosses
z_boss_top = z_roof - WALL
for h in data["holes"]:
    c = kc(h)
    boss = Part.makeCylinder(BOSS_D / 2, 0 - (z_floor + WALL) + 0.01, V(c.x, c.y, z_floor + WALL - 0.01))
    lower = lower.fuse(boss)
    lower = lower.cut(Part.makeCylinder(SCREW_D / 2, 100, V(c.x, c.y, z_floor - 10)))
    top_of_stack = hdmi_top if hdmi_top else T + STANDOFF
    tb = Part.makeCylinder(BOSS_D / 2, z_boss_top - top_of_stack + 0.01, V(c.x, c.y, top_of_stack))
    upper = upper.fuse(tb)
    upper = upper.cut(Part.makeCylinder(SCREW_D / 2, 100, V(c.x, c.y, top_of_stack - 50)))


# ---------------------------------------------------------------- vents (45 degrees)
def vent(ref):
    p = data["parts"][ref]
    c = kc([p["x"], p["y"]])
    sq = box(c.x - VENT_SIZE / 2, c.x + VENT_SIZE / 2, c.y - VENT_SIZE / 2, c.y + VENT_SIZE / 2,
             z_roof - WALL - 1, z_roof + 1)
    slots = None
    n = int(VENT_SIZE * 1.5 / VENT_PITCH)
    for k in range(-n, n + 1):
        s = Part.makeBox(VENT_SIZE * 2, VENT_W, WALL + 2, V(-VENT_SIZE, -VENT_W / 2 + k * VENT_PITCH, z_roof - WALL - 1))
        s.rotate(V(0, 0, 0), V(0, 0, 1), 45)
        s.translate(V(c.x, c.y, 0))
        slots = s if slots is None else slots.fuse(s)
    return slots.common(sq)


for ref in ("U7", "U2"):
    if ref in data["parts"]:
        upper = upper.cut(vent(ref))
for ref in ("SW1", "SW3"):
    if ref in data["parts"]:
        c = kc([data["parts"][ref]["x"], data["parts"][ref]["y"]])
        upper = upper.cut(Part.makeCylinder(PIN_HOLE / 2, WALL + 2, V(c.x, c.y, z_roof - WALL - 1)))

# ---------------------------------------------------------------- output
lower = lower.removeSplitter()
upper = upper.removeSplitter()
for label, shape in (("bottom", lower), ("top", upper)):
    shape.exportStep(os.path.join(out, "%s-%s.step" % (name, label)))
    shape.exportStl(os.path.join(out, "%s-%s.stl" % (name, label)))
doc = App.newDocument(name)
for label, shape in (("Bottom", lower), ("Top", upper), ("Board", board)):
    doc.addObject("Part::Feature", label).Shape = shape
if hdmi_top:
    doc.addObject("Part::Feature", "HDMI").Shape = hdmi
doc.saveAs(os.path.join(out, name + ".FCStd"))

ob = outer.BoundBox
screw_low = WALL + (0 - z_floor - WALL) + T + 4
screw_up = WALL + (z_boss_top - (hdmi_top or T + STANDOFF)) + (hdmi_top and (hdmi_top - T - STANDOFF) or 0) + 4
print("%s: %.1f x %.1f x %.1f mm (floor %.1f, roof %.1f), %d openings" % (
    name, ob.XLength, ob.YLength, z_roof - z_floor, z_floor, z_roof, len(openings)))
print("screws: 4 x M3 from below about %.0f mm, 4 x M3 from above about %.0f mm, 4 standoffs M3 F/F %.0f mm" % (
    screw_low, screw_up, STANDOFF))
print("written to", out)

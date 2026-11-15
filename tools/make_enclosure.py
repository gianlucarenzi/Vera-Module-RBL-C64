#!/usr/bin/env python3
"""Two-shell enclosure for the VERA module, with room for
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
    print("port window: x %.1f..%.1f (KiCad), z %.1f..%.1f mm" % (wx0, wx1, wz0, wz1))
# Card edge fingers: a slot where the board crosses the wall at ENC_CUT
fingers = pl.cut(clip)
for f in fingers.Faces:
    fb = f.BoundBox
    openings.append(box(fb.XMin - 0.5, fb.XMax + 0.5, -ycut - 20, -ycut + 1, -0.6, T + 0.6))
for o in openings:
    lower = lower.cut(o)
    upper = upper.cut(o)
# the port window is cut at the end: it differs in the two variants
z_in_floor = z_floor + WALL         # floor and roof, inner faces
z_in_roof = z_roof - WALL
y_in = y_edge + GAP                 # port wall, inner and outer face
y_out = y_in + WALL
win_open = box(wx0, wx1, y_in - 0.1, y_edge + 20, wz0, wz1) if reach else None

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


# ---------------------------------------------------------------- supports near the fingers
# The M3 holes are all near the port side: near the card edge fingers the
# board is held by a column under it (lower shell) and a peg pressing on it
# from the roof (upper shell), where no part is under / over the board.
SUP_N = 3           # support points across the board width
SUP_COL_D = 6.0     # column under the board
SUP_PEG_D = 5.0     # peg from the roof
SUP_CLEAR = 1.0     # free ring around them
SUP_EDGE = 5.0      # distance from the board edge
SUP_BAND = (3.0, 35.0)   # KiCad y band before ENC_CUT
small = [s.BoundBox for s in parts if s.BoundBox.XLength < 60]   # parts, not boards
below = [b for b in small if b.ZMin < -0.01]
above = [b for b in small if b.ZMax > T + 0.01]
safe = plan.makeOffset2D(-SUP_EDGE, 0)


def free(x, y):
    if not safe.isInside(V(x, y, 0), 0.01, True):
        return False
    r = max(SUP_COL_D, SUP_PEG_D) / 2 + SUP_CLEAR
    for b in below + above:
        if b.XMin - r < x < b.XMax + r and b.YMin - r < y < b.YMax + r:
            return False
    return True


cand = []
for yk in range(int(ycut - SUP_BAND[1]), int(ycut - SUP_BAND[0]) + 1):
    for xk in range(int(bb.XMin), int(bb.XMax) + 1):
        if free(xk, -yk):
            cand.append((xk, -yk))
supports = []
if cand:
    x0 = min(c[0] for c in cand)
    x1 = max(c[0] for c in cand)
    for k in range(SUP_N):
        tx = x0 + (x1 - x0) * (k + 0.5) / SUP_N
        best = min(cand, key=lambda c: (c[0] - tx) ** 2 + (c[1] + ycut) ** 2 * 0.25)
        if all((best[0] - s[0]) ** 2 + (best[1] - s[1]) ** 2 > 15 ** 2 for s in supports):
            supports.append(best)
for x, y in supports:
    col = Part.makeCylinder(SUP_COL_D / 2, 0 - (z_floor + WALL) + 0.01, V(x, y, z_floor + WALL - 0.01))
    lower = lower.fuse(col)
    peg = Part.makeCylinder(SUP_PEG_D / 2, z_roof - WALL - T + 0.01, V(x, y, T))
    upper = upper.fuse(peg)
print("supports near the fingers (KiCad x, y): %s" % ", ".join("(%.0f, %.0f)" % (x, -y) for x, y in supports)
      if supports else "supports near the fingers: no free spot found")

# ---------------------------------------------------------------- back panel (second variant)
# The same shells with the port window down to the floor, closed by a
# separate panel: a plug in the window with a hole for each port, an outer
# flange that stops it on the wall, and snap hooks. Each hook is an arm on
# the floor (or under the roof) going into the case, with a barb that drops
# into a slot through the floor (roof): it is pushed in from outside with
# the case closed, and comes out pressing the barbs up through the slots.
PANEL_TOL = 0.2     # plug to window, each side
PORT_TOL = 0.5      # around each port
FLANGE, FLANGE_T = 1.5, 1.2     # flange overlap on the wall, thickness
NO_MODEL_H = 6.0    # height over the board of a port without a 3D model
SNAP_W, SNAP_L, SNAP_T = 6.0, 10.0, 1.0     # arm width, length, thickness
SNAP_CATCH = 0.7    # barb depth into the slot
SNAP_RAMP = 2.0     # barb length (lead-in ramp)
SNAP_N = 2          # hooks on the floor, as many under the roof
MIN_RIB = 1.2       # thinnest strip of the plug beside a hole


def is_board(b):
    return b.ZLength < T + 0.2 and b.XLength > 20 and b.YLength > 20


win_panel = panel = None
hooks = []
if reach:
    win_panel = box(wx0, wx1, y_in - 0.1, y_edge + 20, z_in_floor, wz1)
    px0, px1, pz0, pz1 = wx0 + PANEL_TOL, wx1 - PANEL_TOL, z_in_floor + PANEL_TOL, wz1 - PANEL_TOL
    panel = box(px0, px1, y_in, y_out, pz0, pz1)
    ob = outer.BoundBox
    panel = panel.fuse(box(max(wx0 - FLANGE, ob.XMin + 0.3), min(wx1 + FLANGE, ob.XMax - 0.3),
                           y_out, y_out + FLANGE_T, z_floor, min(wz1 + FLANGE, z_roof)))
    # port holes: what of each part must pass through the panel (all of it
    # in front of the inner face; the front 1.5 mm of a recessed part)
    rects = []
    for s in parts:
        b = s.BoundBox
        if is_board(b) or b.YMax < y_edge - 2.0 or b.XLength > 60:
            continue
        yc = min(y_in, b.YMax - 1.5)
        try:
            p = s.common(box(b.XMin - 1, b.XMax + 1, yc, b.YMax + 1, b.ZMin - 1, b.ZMax + 1)).BoundBox
        except Exception:
            p = b
        if not p.isValid() or p.XLength < 1.0 or p.ZLength < 1.0 or p.ZMax < T + 0.3:
            continue            # small parts at the edge (passives, pins)
        rects.append((p.XMin, p.XMax, p.ZMin, p.ZMax))
    for ref, pp in sorted(data.get("port_parts", {}).items()):
        if not any(r[0] < pp["x1"] and r[1] > pp["x0"] and r[3] > T for r in rects):
            rects.append((pp["x0"], pp["x1"], T, T + NO_MODEL_H))
            print("port %s without a 3D model: hole %.0f mm high" % (ref, NO_MODEL_H))
    rects = [(x0 - PORT_TOL, x1 + PORT_TOL, z0 - PORT_TOL, z1 + PORT_TOL) for x0, x1, z0, z1 in rects]
    # no strip under MIN_RIB between a hole and the edge of the plug (it would
    # not print): the hole goes to the window edge, the flange stays whole
    rects = [(x0 if x0 - px0 >= MIN_RIB else wx0 - 0.1, x1 if px1 - x1 >= MIN_RIB else wx1 + 0.1,
              z0 if z0 - pz0 >= MIN_RIB else z_in_floor - 0.1, z1 if pz1 - z1 >= MIN_RIB else wz1 + 0.1)
             for x0, x1, z0, z1 in rects]
    for x0, x1, z0, z1 in rects:
        panel = panel.cut(box(x0, x1, y_in - 1, y_out + FLANGE_T + 1, z0, z1))

    # snap hooks where the arm, bent by the barb, touches nothing
    obst = [s.BoundBox for s in parts]
    for h in data["holes"]:
        c = kc(h)
        obst.append(App.BoundBox(c.x - BOSS_D / 2, c.y - BOSS_D / 2, z_floor, c.x + BOSS_D / 2, c.y + BOSS_D / 2, z_roof))
    for x, y in supports:
        obst.append(App.BoundBox(x - SUP_COL_D / 2, y - SUP_COL_D / 2, z_floor, x + SUP_COL_D / 2, y + SUP_COL_D / 2, z_roof))
    flex = SNAP_CATCH + PANEL_TOL       # the arm lifts by the barb height
    zone = {"floor": (z_in_floor, pz0 + SNAP_T + flex + 0.5),
            "roof": (pz1 - SNAP_T - flex - 0.5, z_in_roof)}
    root = {"floor": (pz0, pz0 + SNAP_T + 1.5), "roof": (pz1 - SNAP_T - 1.5, pz1)}

    def hook_free(x, where):
        xa, xb = x - SNAP_W / 2 - 0.5, x + SNAP_W / 2 + 0.5
        za, zb = zone[where]
        for b in obst:
            if b.XMin < xb and b.XMax > xa and b.YMin < y_in and b.YMax > y_in - SNAP_L - 0.5 \
                    and b.ZMin < zb and b.ZMax > za:
                return False
        ra, rb = root[where]
        return not any(r[0] < xb + 0.5 and r[1] > xa - 0.5 and r[2] < rb and r[3] > ra for r in rects)

    def hook(x, where):
        """arm + barb (on the panel) and slot (in the shell) of one hook"""
        ya, yc = y_in - SNAP_L, y_in - SNAP_L + SNAP_RAMP
        if where == "floor":
            arm = box(x - SNAP_W / 2, x + SNAP_W / 2, ya, y_in + 0.01, pz0, pz0 + SNAP_T)
            zt, zb = pz0 + 0.01, z_in_floor - SNAP_CATCH
            slot = box(x - SNAP_W / 2 - 0.3, x + SNAP_W / 2 + 0.3, ya - 0.3, yc + 0.2, z_floor - 1, z_in_floor + 0.01)
        else:
            arm = box(x - SNAP_W / 2, x + SNAP_W / 2, ya, y_in + 0.01, pz1 - SNAP_T, pz1)
            zt, zb = pz1 - 0.01, z_in_roof + SNAP_CATCH
            slot = box(x - SNAP_W / 2 - 0.3, x + SNAP_W / 2 + 0.3, ya - 0.3, yc + 0.2, z_in_roof - 0.01, z_roof + 1)
        # lead-in ramp towards the inside, square catch face towards the port side
        prof = [V(x - SNAP_W / 2, ya, zt), V(x - SNAP_W / 2, yc, zt), V(x - SNAP_W / 2, yc, zb)]
        barb = Part.Face(Part.makePolygon(prof + [prof[0]])).extrude(V(SNAP_W, 0, 0))
        return arm.fuse(barb), slot

    for where in ("floor", "roof"):
        cand = [px0 + SNAP_W / 2 + 1 + 0.5 * k for k in range(int((px1 - px0 - SNAP_W - 2) / 0.5) + 1)]
        cand = [x for x in cand if hook_free(x, where)]
        chosen = []
        for k in range(SNAP_N):
            tx = px0 + (px1 - px0) * (0.12 + 0.76 * k / max(SNAP_N - 1, 1))
            for x in sorted(cand, key=lambda c: abs(c - tx)):
                if all(abs(x - c) > SNAP_W + 10 for c in chosen):
                    chosen.append(x)
                    break
        for x in chosen:
            hooks.append((where, x) + hook(x, where))
        print("back panel hooks, %s (KiCad x): %s" % (where, ", ".join("%.1f" % x for x in chosen) or "no free spot found"))
    for where, x, h, slot in hooks:
        panel = panel.fuse(h)
    print("back panel: %d port holes, %d hooks" % (len(rects), len(hooks)))

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
def light(shape):
    """A light stand-in of a board, for a document that opens fast on a
    small machine: the PCB outline without holes, a box for each part."""
    solids = shape.Solids
    pcb = max(solids, key=lambda s: s.BoundBox.XLength * s.BoundBox.YLength)
    top = max((f for f in pcb.Faces if abs(f.normalAt(0, 0).z) > 0.99), key=lambda f: f.BoundBox.ZMax)
    boxes = [Part.Face(top.OuterWire).extrude(V(0, 0, -pcb.BoundBox.ZLength))]
    for s in solids:
        b = s.BoundBox
        if s is pcb or b.XLength * b.YLength < 0.5 or min(b.XLength, b.YLength, b.ZLength) < 0.05:
            continue
        boxes.append(box(b.XMin, b.XMax, b.YMin, b.YMax, b.ZMin, b.ZMax))
    return Part.makeCompound(boxes)


board_light = light(board)
hdmi_light = light(hdmi) if hdmi_top else None

# two variants: the open port window (name) and the back panel (name-backpanel)
variants = [(name, win_open, [], None)]
if panel is not None:
    variants.append((name + "-backpanel", win_panel, hooks, panel.removeSplitter()))
for vname, window, vhooks, vpanel in variants:
    lo, up = lower, upper
    if window is not None:
        lo, up = lo.cut(window), up.cut(window)
    for where, x, h, slot in vhooks:
        if where == "floor":
            lo = lo.cut(slot)
        else:
            up = up.cut(slot)
    lo, up = lo.removeSplitter(), up.removeSplitter()
    pieces = [("bottom", lo), ("top", up)] + ([("panel", vpanel)] if vpanel else [])
    for label, shape in pieces:
        shape.exportStep(os.path.join(out, "%s-%s.step" % (vname, label)))
        shape.exportStl(os.path.join(out, "%s-%s.stl" % (vname, label)))
    # the full document, and a light one (boards as outline and part boxes)
    for suffix, bd, hd in (("", board, hdmi if hdmi_top else None), ("-light", board_light, hdmi_light)):
        doc = App.newDocument((vname + suffix).replace("-", "_"))
        for label, shape in [("Bottom", lo), ("Top", up), ("Board", bd)] + ([("Panel", vpanel)] if vpanel else []):
            doc.addObject("Part::Feature", label).Shape = shape
        if hd is not None:
            doc.addObject("Part::Feature", "HDMI").Shape = hd
        doc.saveAs(os.path.join(out, vname + suffix + ".FCStd"))
        App.closeDocument(doc.Name)
    print("variant %s: %s" % (vname, ", ".join(p[0] for p in pieces)))

ob = outer.BoundBox
screw_low = WALL + (0 - z_floor - WALL) + T + 4
screw_up = WALL + (z_boss_top - (hdmi_top or T + STANDOFF)) + (hdmi_top and (hdmi_top - T - STANDOFF) or 0) + 4
print("%s: %.1f x %.1f x %.1f mm (floor %.1f, roof %.1f), %d openings" % (
    name, ob.XLength, ob.YLength, z_roof - z_floor, z_floor, z_roof, len(openings) + (1 if reach else 0)))
print("screws: 4 x M3 from below about %.0f mm, 4 x M3 from above about %.0f mm, 4 standoffs M3 F/F %.0f mm" % (
    screw_low, screw_up, STANDOFF))
print("written to", out)

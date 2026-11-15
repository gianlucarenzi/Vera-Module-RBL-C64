# -*- coding: utf-8 -*-
"""Assembly of the enclosure made by tools/make_enclosure.py, step by step:
lower shell, board, standoffs, VERA-HDMI-Expansion, upper shell closing
and, in the back panel variant, the panel snapping into the port side.

As a FreeCAD macro (Macro > Macros..., or run it from the Python console):
open enclosure/<name>.FCStd first, then run this file: it animates the
active document. The boards are drawn as light stand-ins (outline and part
boxes), the full STEP redraws too slowly on a small machine; ENC_FULL=1
keeps the full boards.

Frames for a GIF, without a screen (FreeCAD GUI on a virtual display):
  ENC_DOC=enclosure/X.FCStd ENC_FRAMES=/tmp/frames \\
      xvfb-run -a -s "-screen 0 1280x1024x24" freecad tools/enclosure_assembly.py
  convert -delay 6 -loop 0 /tmp/frames/*.png enclosure/X-assembly.gif

Only FreeCAD 0.19+ GUI calls are used (Placement, ViewObject, saveImage, the
Coin camera through pivy).
"""
import os
import time

import FreeCAD as App
import FreeCADGui as Gui
import Part

V = App.Vector
frames = os.environ.get("ENC_FRAMES")
if os.environ.get("ENC_DOC"):
    App.openDocument(os.environ["ENC_DOC"])
doc = App.ActiveDocument
obj = {o.Label: o for o in doc.Objects}
bottom, top, board = obj["Bottom"], obj["Top"], obj["Board"]
hdmi = obj.get("HDMI")
panel = obj.get("Panel")

# standoffs (M3 F/F 14 mm, hex 5.5 mm drawn as a cylinder) on the holes
if "Standoffs" not in obj:
    t = 1.6
    st = None
    holes = []
    # the holes are the screw holes of the lower shell bosses: find them as
    # the circular edges of radius 1.6 at the floor
    for e in bottom.Shape.Edges:
        if hasattr(e.Curve, "Radius") and abs(e.Curve.Radius - 1.6) < 0.01:
            c = e.Curve.Center
            key = (round(c.x, 1), round(c.y, 1))
            if key not in [h[0] for h in holes]:
                holes.append((key, c))
    for key, c in holes:
        cyl = Part.makeCylinder(2.75, 14.0, V(c.x, c.y, t))
        st = cyl if st is None else st.fuse(cyl)
    so = doc.addObject("Part::Feature", "Standoffs")
    so.Shape = st
    obj["Standoffs"] = so
standoffs = obj["Standoffs"]



def light(o):
    """A light stand-in of a board for the live animation: the PCB outline
    without holes and vias, a box for each part. Redrawing the full STEP
    takes seconds per frame on a small machine; ENC_FULL=1 keeps it."""
    solids = o.Shape.Solids
    pcb = max(solids, key=lambda s: s.BoundBox.XLength * s.BoundBox.YLength)
    top = max((f for f in pcb.Faces if abs(f.normalAt(0, 0).z) > 0.99),
              key=lambda f: f.BoundBox.ZMax)
    plate = Part.Face(top.OuterWire).extrude(V(0, 0, -pcb.BoundBox.ZLength))
    boxes = [plate]
    for s in solids:
        if s is pcb:
            continue
        b = s.BoundBox
        if b.XLength * b.YLength < 0.5 or min(b.XLength, b.YLength, b.ZLength) < 0.05:
            continue
        boxes.append(Part.makeBox(b.XLength, b.YLength, b.ZLength, V(b.XMin, b.YMin, b.ZMin)))
    stand_in = doc.addObject("Part::Feature", o.Label + "_light")
    stand_in.Shape = Part.makeCompound(boxes)       # already where the board is
    o.ViewObject.Visibility = False
    return stand_in


if not frames and os.environ.get("ENC_FULL") != "1":
    board = light(board)
    if hdmi is not None:
        hdmi = light(hdmi)

colours = {"Bottom": (0.25, 0.25, 0.28), "Top": (0.20, 0.35, 0.65), "Board": (0.10, 0.45, 0.25),
           "HDMI": (0.10, 0.40, 0.55), "Standoffs": (0.85, 0.85, 0.80), "Panel": (0.80, 0.45, 0.15)}
for o in (bottom, top, board, hdmi, standoffs, panel):
    if o is not None:
        o.ViewObject.ShapeColor = colours[o.Label.replace("_light", "")]
        o.ViewObject.Visibility = True
        o.ViewObject.LineColor = (0.1, 0.1, 0.1)
top.ViewObject.Transparency = 35

view = Gui.ActiveDocument.ActiveView
# (part, start offset): from above, the panel from the port side (+Y)
STEPS = [(board, V(0, 0, 70)), (standoffs, V(0, 0, 50)), (hdmi, V(0, 0, 90)), (top, V(0, 0, 120)),
         (panel, V(0, 60, 0))]


# a shape moved with translated() keeps that move in its Placement (the
# STEP of each board is moved onto the board outline): add to it, never
# replace it
home = {o.Name: o.Placement.copy() for o in (bottom, top, board, hdmi, standoffs, panel) if o is not None}


def place(o, d):
    if o is not None:
        h = home[o.Name]
        o.Placement = App.Placement(h.Base + d, h.Rotation)


# Camera set once, on the whole assembly exploded and closed: orthographic,
# pointed at its centre and sized on it, so the frames do not depend on the
# window size (fitAll does, and the view commands animate the camera). From
# the card edge side like an isometric view; with a back panel from the port
# side, to see the panel going in.
look = V(-0.55, -0.65, -0.52) if panel is not None else V(-1, 1, -1)
look.normalize()
movers = [o for o, d in STEPS if o is not None]
bb = App.BoundBox()
for o in [bottom] + movers:
    bb.add(o.Shape.BoundBox)                    # closed
for o, d in STEPS:
    if o is not None:
        e = App.BoundBox(o.Shape.BoundBox)
        e.move(d)
        bb.add(e)                               # exploded
right = look.cross(V(0, 0, 1))
right.normalize()
up = right.cross(look)
corners = [V(x, y, z) for x in (bb.XMin, bb.XMax) for y in (bb.YMin, bb.YMax) for z in (bb.ZMin, bb.ZMax)]
c = bb.Center
w = max(abs((p - c).dot(right)) for p in corners) * 2
h = max(abs((p - c).dot(up)) for p in corners) * 2
IMG_W, IMG_H = 960, 720


def camera():
    from pivy import coin
    view.setCameraType("Orthographic")
    cam = view.getCameraNode()
    pos = c - look * (bb.DiagonalLength * 2)
    cam.position.setValue(pos.x, pos.y, pos.z)
    cam.pointAt(coin.SbVec3f(c.x, c.y, c.z), coin.SbVec3f(0, 0, 1))
    cam.nearDistance.setValue(1)
    cam.farDistance.setValue(bb.DiagonalLength * 5)
    cam.height.setValue(max(h, w * IMG_H / IMG_W) * 1.06)


for o, d in STEPS:
    place(o, d)
Gui.updateGui()
camera()
n = [0]


def shot():
    Gui.updateGui()
    if frames:
        os.makedirs(frames, exist_ok=True)
        view.saveImage(os.path.join(frames, "f%04d.png" % n[0]), IMG_W, IMG_H, "White")
    else:
        time.sleep(0.04)
    n[0] += 1


for _ in range(8):
    shot()
for o, d in STEPS:
    if o is None:
        continue
    for k in range(1, 21):
        place(o, d * (1 - k / 20.0) ** 2)       # slows down at the end
        shot()
    for _ in range(4):
        shot()
for _ in range(15):
    shot()
top.ViewObject.Transparency = 0
for _ in range(20):
    shot()
if frames:
    print("frames:", n[0], "in", frames)
    os._exit(0)

# -*- coding: utf-8 -*-
"""Assembly of the enclosure made by tools/make_enclosure.py, step by step:
lower shell, board, standoffs, VERA-HDMI-Expansion, upper shell closing.

As a FreeCAD macro (Macro > Macros..., or run it from the Python console):
open enclosure/<name>.FCStd first, then run this file: it animates the
active document. The boards are drawn as light stand-ins (outline and part
boxes), the full STEP redraws too slowly on a small machine; ENC_FULL=1
keeps the full boards.

Frames for a GIF, without a screen (FreeCAD GUI on a virtual display):
  ENC_DOC=enclosure/X.FCStd ENC_FRAMES=/tmp/frames \\
      xvfb-run -a -s "-screen 0 1280x1024x24" freecad tools/enclosure_assembly.py
  convert -delay 6 -loop 0 /tmp/frames/*.png enclosure/X-assembly.gif

Only FreeCAD 0.19+ GUI calls are used (Placement, ViewObject, saveImage).
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
           "HDMI": (0.10, 0.40, 0.55), "Standoffs": (0.85, 0.85, 0.80)}
for o in (bottom, top, board, hdmi, standoffs):
    if o is not None:
        o.ViewObject.ShapeColor = colours[o.Label.replace("_light", "")]
        o.ViewObject.Visibility = True
        o.ViewObject.LineColor = (0.1, 0.1, 0.1)
top.ViewObject.Transparency = 35

view = Gui.ActiveDocument.ActiveView
STEPS = [(board, 70.0), (standoffs, 50.0), (hdmi, 90.0), (top, 120.0)]


# a shape moved with translated() keeps that move in its Placement (the
# STEP of each board is moved onto the board outline): add to it, never
# replace it
home = {o.Name: o.Placement.copy() for o in (bottom, top, board, hdmi, standoffs) if o is not None}


def place(o, dz):
    if o is not None:
        h = home[o.Name]
        o.Placement = App.Placement(h.Base + V(0, 0, dz), h.Rotation)


# exploded start, camera fitted on it once
for o, dz in STEPS:
    place(o, dz)
view.viewIsometric()
Gui.updateGui()
view.fitAll()
n = [0]


def shot():
    Gui.updateGui()
    if frames:
        os.makedirs(frames, exist_ok=True)
        view.saveImage(os.path.join(frames, "f%04d.png" % n[0]), 960, 720, "White")
    else:
        time.sleep(0.04)
    n[0] += 1


for _ in range(8):
    shot()
for o, dz in STEPS:
    if o is None:
        continue
    for k in range(1, 21):
        place(o, dz * (1 - k / 20.0) ** 2)      # slows down at the end
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

# FreeCAD (GUI, under xvfb-run, for the colours; run by tools/fc_assembly.sh):
# from the enclosure of a VERA module repository, two documents in
# $REPO/enclosure:
#   <NAME>-module.FCStd        the module as one App::Part: Board, HDMI, the
#                              four standoffs, Bottom, Top, Panel; origin at
#                              the centre of the card edge fingers' tip, on
#                              the bottom face of the PCB
#   <NAME>-in-<COMPUTER>.FCStd the computer's covers and keyboard (meshes of
#                              the render's desk scene, computer coordinates:
#                              rear edge at y 0, front +Y, table z 0) with
#                              the module plugged in as in the teaser
# Environment: REPO, NAME (VERA-RBL-C64), COMPUTER (C64), CTX (folder of
# tools/fc_context.py: placement.json and the STL meshes); optional:
#   MB        folder of tools/wrl2stl.py (the computer's motherboard)
#   MB_PLACE  [a, b, c]: motherboard VRML x, y, z -> computer -x+a, -y+b, z+c
#   MODULE_T  [x, y, z]: the module's translation instead of the teaser's
#             (the same rotation)
import json
import math
import os

import FreeCAD as App
import Mesh
import Part

try:
    import FreeCADGui as Gui
    GUI = App.GuiUp
except ImportError:
    GUI = False

env = os.environ
REPO, NAME, COMPUTER, CTX = env["REPO"], env["NAME"], env["COMPUTER"], env["CTX"]
V = App.Vector
place = json.load(open(os.path.join(CTX, "placement.json")))
src = App.openDocument(os.path.join(REPO, "enclosure", NAME + "-enclosure-backpanel.FCStd"))
shapes = {o.Name: o.Shape.copy() for o in src.Objects if o.Name in ("Board", "HDMI", "Bottom", "Top", "Panel")}
App.closeDocument(src.Name)

T, H = place["thickness"], place["standoff"]


def hex_prism(x, y, z0, z1, af=5.5):
    r = af / 2 / math.cos(math.pi / 6)
    pts = [V(x + r * math.cos(math.pi / 6 + k * math.pi / 3), y + r * math.sin(math.pi / 6 + k * math.pi / 3), z0)
           for k in range(6)]
    return Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(V(0, 0, z1 - z0))


COLOURS = {"Board": (0.12, 0.31, 0.21), "HDMI": (0.10, 0.22, 0.40), "Bottom": (0.89, 0.85, 0.78),
           "Top": (0.89, 0.85, 0.78), "Panel": (0.84, 0.80, 0.72), "Standoff": (0.79, 0.64, 0.30)}


def colour(obj, rgb, transparency=0):
    if GUI and obj.ViewObject:
        obj.ViewObject.ShapeColor = tuple(rgb)
        obj.ViewObject.Transparency = transparency


def module(doc, label):
    part = doc.addObject("App::Part", label)
    for n in ("Board", "HDMI"):
        o = doc.addObject("Part::Feature", n)
        o.Shape = shapes[n]
        part.addObject(o)
        colour(o, COLOURS[n])
    so = doc.addObject("App::DocumentObjectGroup", "Standoffs")
    part.addObject(so)
    for k, (x, y) in enumerate(place["holes"]):
        o = doc.addObject("Part::Feature", "Standoff%d" % (k + 1))
        o.Shape = hex_prism(x, -y, T, T + H)
        o.Label = "Standoff%d_M3_FF_%gmm" % (k + 1, H)
        so.addObject(o)
        colour(o, COLOURS["Standoff"])
    for n in ("Bottom", "Top", "Panel"):
        o = doc.addObject("Part::Feature", n)
        o.Shape = shapes[n]
        part.addObject(o)
        colour(o, COLOURS[n])
    return part


label = NAME.replace("-", "_") + "_module"

# 1. the module alone, origin at the fingers
doc = App.newDocument(NAME.replace("-", "_") + "_module")
part = module(doc, label)
fx, fy, fz = place["finger"]
part.Placement = App.Placement(V(-fx, -fy, -fz), App.Rotation())
doc.recompute()
out1 = os.path.join(REPO, "enclosure", NAME + "-module.FCStd")
doc.saveAs(out1)
App.closeDocument(doc.Name)

# 2. plugged into the computer
doc = App.newDocument(NAME.replace("-", "_") + "_in_" + COMPUTER)
comp = doc.addObject("App::DocumentObjectGroup", COMPUTER)
for name, p in sorted(place["parts"].items()):
    if p["tris"] < 20:                      # the dark planes under the keys
        continue
    m = doc.addObject("Mesh::Feature", name)
    m.Mesh = Mesh.Mesh(os.path.join(CTX, name + ".stl"))
    comp.addObject(m)
    if GUI and m.ViewObject and "rgb" in p:
        m.ViewObject.ShapeColor = tuple(p["rgb"])
if env.get("MB"):
    # the motherboard (VRML converted by wrl2stl.py), one mesh per colour,
    # on the bosses of the case: VRML x, y, z -> computer -x+a, -y+b, z+c
    mbp = json.loads(env["MB_PLACE"])
    mb = doc.addObject("App::DocumentObjectGroup", COMPUTER + "_motherboard")
    for k, q in enumerate(json.load(open(os.path.join(env["MB"], "parts.json")))):
        m = doc.addObject("Mesh::Feature", "MB_%02d" % k)
        m.Mesh = Mesh.Mesh(os.path.join(env["MB"], q["file"]))
        m.Placement = App.Placement(V(*mbp), App.Rotation(V(0, 0, 1), 180))
        mb.addObject(m)
        if GUI and m.ViewObject:
            m.ViewObject.ShapeColor = tuple(q["rgb"])
part = module(doc, label)
R, t = place["module_rotation"], place["module_translation"]
if env.get("MODULE_T"):
    t = json.loads(env["MODULE_T"])
mat = App.Matrix(R[0][0], R[0][1], R[0][2], t[0],
                 R[1][0], R[1][1], R[1][2], t[1],
                 R[2][0], R[2][1], R[2][2], t[2],
                 0, 0, 0, 1)
part.Placement = App.Placement(mat)
doc.recompute()
out2 = os.path.join(REPO, "enclosure", "%s-in-%s.FCStd" % (NAME, COMPUTER))
doc.saveAs(out2)
if GUI:
    Gui.activeDocument().activeView().viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    doc.save()
print("FCASM written", out1, out2, "gui" if GUI else "no gui")
App.closeDocument(doc.Name)
if GUI:
    os._exit(0)

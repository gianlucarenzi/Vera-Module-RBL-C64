# STEP -> VRML with the colours, for FreeCAD 0.19+ with its GUI (the VRML
# export and the colours belong to the GUI; run it on a virtual display):
#
#   STEP2WRL_IN=board.step STEP2WRL_OUT=board.wrl xvfb-run -a freecad step2wrl.py
#
# - the STEP colours are read by FreeCAD 0.19 / OCC 7.5 as linear RGB and come
#   out too dark: converted back to sRGB
# - the VRML export writes one material per object: every object is split
#   into one object per face colour
# - surfaces only (no edge lines), as in the KiCad VRML
# - placed like the KiCad VRML export: board centred on the origin (x, y and
#   z), unit 0.1 inch (scale 1/2.54 from mm)
# Exit status 0 when the file is written, 1 otherwise; messages in
# STEP2WRL_LOG (default: <out>.log), for the calling script to show.
import gzip
import os
import traceback

src = os.environ.get("STEP2WRL_IN", "")
dst = os.environ.get("STEP2WRL_OUT", "")
logname = os.environ.get("STEP2WRL_LOG", dst + ".log")
log = open(logname, "w")
ok = False


def p(*a):
    log.write(" ".join(str(x) for x in a) + "\n")
    log.flush()


def srgb(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


try:
    import FreeCAD
    import FreeCADGui
    import ImportGui
    import Part

    if not src or not os.path.exists(src) or not dst:
        raise SystemExit("STEP2WRL_IN / STEP2WRL_OUT not set or input missing")
    doc = FreeCAD.newDocument("step")
    ImportGui.insert(src, doc.Name)
    doc.recompute()

    out = FreeCAD.newDocument("vrml")
    pieces = 0
    board = None                  # the thin object with the largest XY area
    for o in doc.Objects:
        if not o.isDerivedFrom("Part::Feature") or o.ViewObject is None:
            continue
        shape = o.Shape.copy()
        shape.Placement = o.getGlobalPlacement()
        faces = shape.Faces
        if not faces:
            continue
        bb = shape.BoundBox
        if bb.ZLength <= 2.0 and (board is None or bb.XLength * bb.YLength > board.XLength * board.YLength):
            board = bb
        cols = o.ViewObject.DiffuseColor
        if len(cols) != len(faces):
            cols = [o.ViewObject.ShapeColor] * len(faces)
        groups = {}
        for f, c in zip(faces, cols):
            key = tuple(round(srgb(x), 4) for x in c[:3])
            groups.setdefault(key, []).append(f)
        for key, fl in groups.items():
            n = out.addObject("Part::Feature", "P%d" % pieces)
            n.Shape = Part.makeCompound(fl)
            n.ViewObject.ShapeColor = key
            n.ViewObject.DisplayMode = "Shaded"
            pieces += 1
    out.recompute()
    if board is None:
        raise SystemExit("board not found in the STEP")

    tmp = dst + ".tmp.wrl"        # FreeCAD picks the exporter from the extension
    FreeCADGui.export(out.Objects, tmp)
    raw = open(tmp, "rb").read()
    os.remove(tmp)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    body = raw.decode("utf-8").split("\n", 1)[1]
    s = 1 / 2.54
    c = board.Center
    with open(dst, "w") as f:
        f.write("#VRML V2.0 utf8\n")
        f.write("# %s, converted by step2wrl.py (FreeCAD %s)\n" % (os.path.basename(src), ".".join(FreeCAD.Version()[:2])))
        f.write("# unit 0.1 inch, board centred on the origin, as the KiCad VRML export\n")
        f.write("Transform {\n  scale %g %g %g\n  translation %g %g %g\n  children [\n"
                % (s, s, s, -c.x * s, -c.y * s, -c.z * s))
        f.write(body)
        f.write("\n  ]\n}\n")
    p("step2wrl: %d pieces, board %.1f x %.1f mm, %s written" % (pieces, board.XLength, board.YLength, dst))
    ok = True
except BaseException:
    p(traceback.format_exc())
log.close()
os._exit(0 if ok else 1)

# -*- coding: utf-8 -*-
"""The desk of the second part of the assembly video (tools/render_enclosure.py,
RENDER_MODE=desk): the computer the module plugs into, two monitors, their
screens. Imported by render_enclosure.py inside Blender.

The Atari 130XE comes from the 3D models of 3DRepo (Atari/XE, DESK_ASSETS):
the top cover (Top_Case_Model_A, the rhomboid function keys) and the bottom
cover, whole ("-big"), the rhomboid function keycap; the keyboard is built
here from the layout of tools/make_screens.py (xe-keys.json, KLE units) with
the keycap of the A130KB_MX keyboard (tools/keyboards/keycap-1u.stl) and its
legends (xe-keys.png, xe-fn.png).

Computer coordinates, mm: X across (+X on the left of who types), Y from
the rear (0) to the front, Z up from the table (0).
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

MM = 0.001
U = 19.05                                   # key unit, mm


def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def plastic(name, hex_, rough=0.45):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb(hex_) + (1,)
    b.inputs["Roughness"].default_value = rough
    return m


def legend_material(name, cap_hex, image_path, rough=0.4):
    """cap colour with the legends of a transparent texture over it (UV)"""
    m = plastic(name, cap_hex, rough)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path)
    tex.interpolation = "Cubic"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = srgb(cap_hex) + (1,)
    nt.links.new(tex.outputs["Alpha"], mix.inputs["Factor"])
    nt.links.new(tex.outputs["Color"], mix.inputs["B"])
    nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
    return m


def read_stl(path):
    """vertices and faces of an STL (Blender's importer, then removed)"""
    before = set(bpy.data.objects)
    bpy.ops.wm.stl_import(filepath=path)
    ob = (set(bpy.data.objects) - before).pop()
    v = [tuple(p.co) for p in ob.data.vertices]
    f = [list(p.vertices) for p in ob.data.polygons]
    me = ob.data
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return v, f


def outward(me):
    """the normals of a closed mesh pointing out (for booleans)"""
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()


def mesh(name, verts, faces, mat, uvs=None, parent=None, smooth=0.6):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    if uvs is not None:
        layer = me.uv_layers.new(name="UV")
        for poly in me.polygons:
            for li in poly.loop_indices:
                layer.data[li].uv = uvs[me.loops[li].vertex_index]
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(mat)
    if parent:
        ob.parent = parent
    if smooth:
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        try:
            bpy.ops.object.shade_smooth_by_angle(angle=smooth)
        except Exception:
            bpy.ops.object.shade_smooth()
    return ob


def import_stl(path, mat, parent, rot_z=0.0):
    before = set(bpy.data.objects)
    bpy.ops.wm.stl_import(filepath=path)
    ob = (set(bpy.data.objects) - before).pop()
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    ob.rotation_euler = (0, 0, math.radians(rot_z))
    ob.parent = parent
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=0.5)
    except Exception:
        pass
    return ob


# ---------------------------------------------------------------- Atari 130XE
XE = {
    "case": "9DA09A",            # RAL 7038 agate grey covers, 13% darker
    "key": "CDCCC6",             # white keycaps (13% darker), black legends
    "fn": "9DA09A",              # function keys: as the covers, white legends
    # the keyboard opening of the top cover: left edge (+X) and rear edge of
    # key (0, 0) of the layout, the slope of the keyboard (the bezel, from
    # z 37 at y 120 to z 11 at y 228), the keycap tops above the bezel
    "kb_x0": 145.0, "kb_y0": 128.0, "kb_z0": 41.1, "kb_slope": -26.0 / 108.0, "kb_rise": 3.5,
    "space_x": -1.0,             # centre of the spacebar (the front opening)
    # the parallelogram opening of the five function keys: centre line y,
    # first key (HELP, on the left of who types) centre x, pitch, top z
    "fn_y": 107.5, "fn_x0": -22.3, "fn_pitch": -28.6, "fn_z": 44.0,
    # the cartridge + ECI opening at the rear (y = 0): the motherboard edge,
    # between the two slots, in computer coordinates (from the rear view of
    # the covers): the cartridge slot centre x, the ECI slot centre x, z
    "slot_cart_x": -30.8, "slot_eci_x": 19.0, "slot_z": 13.75,
    # (kb_z0 and fn_z: raised by 6 and 3 mm by hand in FreeCAD)
    # the top cover on the bottom one, as placed by hand in FreeCAD
    # (A130XE-assembly.FCStd): the top file moved by this, the bottom file
    # turned 90 degrees; the keyboard and the function keys move with the top
    "top_offset": (0.0, -3.0, 12.0),
    # the module's fingers this far (mm) past the rear edge: its case goes
    # into the cartridge + ECI recess of the rear (10 mm more than the C64)
    "insert": 28.0,
}


def build_xe(assets, screens, keyboards):
    """the 130XE as children of an empty (computer coordinates, scaled to
    metres); returns (root, info)"""
    root = bpy.data.objects.new("atari130xe", None)
    bpy.context.scene.collection.objects.link(root)
    root.scale = (MM, MM, MM)
    case = plastic("xe_case", XE["case"], 0.5)
    import_stl(os.path.join(assets, "Bottom_Case", "A130XE-bottom-big.stl"), case, root, rot_z=90)
    top = bpy.data.objects.new("xe_top", None)       # the top cover and all on it
    bpy.context.scene.collection.objects.link(top)
    top.parent = root
    top.location = XE["top_offset"]
    import_stl(os.path.join(assets, "Top_Case_Model_A", "A130XE-top-big.stl"), case, top)

    # the keyboard: one keycap shape (A130KB_MX, 18.2 x 18.2 mm, 7.9 high,
    # Y up in its file) stretched to each key's width
    cv, cf = read_stl(os.path.join(keyboards, "keycap-1u.stl"))
    cap = [(x, -z, y) for x, y, z in cv]                 # Y up -> Z up
    lay = json.load(open(os.path.join(screens, "xe-keys.json")))["keys"]
    cols = max(k[0] + k[2] for k in lay)
    rows = max(k[1] + k[3] for k in lay)
    verts, faces, uvs = [], [], []
    tilt = Matrix.Rotation(math.atan(XE["kb_slope"]), 4, "X")
    pivot = Vector((0, XE["kb_y0"], XE["kb_z0"] - 7.9 + XE["kb_rise"]))
    for kx, ky, kw, kh, _ in lay:
        cx = XE["kb_x0"] - (kx + kw / 2) * U
        if kw >= 6:
            cx = XE["space_x"]
        cy = XE["kb_y0"] + (ky + kh / 2) * U
        sx = (kw * U - 0.85) / 18.2
        sy = (kh * U - 0.85) / 18.2
        base = len(verts)
        for x, y, z in cap:
            px, py = cx + x * sx, cy + y * sy
            # the legends: layout units of the flat keyboard
            ux = (XE["kb_x0"] - px) / U if kw < 6 else kx + kw / 2 + (cx - px) / U
            uy = (py - XE["kb_y0"]) / U
            uvs.append((ux / cols, 1 - uy / rows))
            p = Vector((px, py, z)) - Vector((0, XE["kb_y0"], 0))
            p = tilt @ p + pivot
            verts.append(tuple(p))
        faces += [[base + i for i in f] for f in cf]
    mesh("xe_keys", verts, faces, legend_material("xe_key", XE["key"], os.path.join(screens, "xe-keys.png")),
         uvs, top)

    # a dark well under the keys (the inside of the computer is not modelled)
    well = [(-150, 125, 0), (150, 125, 0), (150, 226, 0), (-150, 226, 0)]
    wv = []
    for x, y, _ in well:
        p = tilt @ Vector((x, y - XE["kb_y0"], 0)) + Vector((0, XE["kb_y0"], XE["kb_z0"] - 9))
        wv.append(tuple(p))
    mesh("xe_well", wv, [[0, 1, 2, 3]], plastic("xe_well", "151515", 0.8), None, top, smooth=0)

    # the five rhomboid function keys: printed upside down in their file,
    # turned over (X axis), each with its cell of xe-fn.png
    fv, ff = read_stl(os.path.join(assets, "AtariXE-Func-5.55-4.25-1.53.stl"))
    fv = [(x, -y, -z) for x, y, z in fv]
    xs = [p[0] for p in fv]
    ys = [p[1] for p in fv]
    ztop = max(p[2] for p in fv)
    xm, ym = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    depth = max(ys) - min(ys)
    # the slant of the rhombus (its centre moves by `slant` mm per mm of Y):
    # 45 degrees, the direction of the file's vertices
    n = len(fv)
    cov = sum((x - xm) * (y - ym) for x, y, z in fv) / n
    slant = math.copysign(1.0, cov)
    flat = (max(xs) - min(xs)) - abs(slant) * depth          # width across the rhombus
    fmat = legend_material("xe_fn", XE["fn"], os.path.join(screens, "xe-fn.png"))
    for i in range(5):
        cx = XE["fn_x0"] + i * XE["fn_pitch"]
        v, uv = [], []
        for x, y, z in fv:
            # the cell of key i (1.5 units of 7.5) across the rhombus at its
            # height; +X is on the left of who types, so u grows to -X
            across = -(x - xm - slant * (y - ym)) / flat + 0.5
            uv.append(((i + across) * 1.5 / 7.5, 1 - (y - min(ys)) / depth))
            p = tilt @ Vector((cx + x, y, z - ztop)) + Vector((0, XE["fn_y"], XE["fn_z"]))
            v.append(tuple(p))
        mesh("xe_fn%d" % i, v, ff, fmat, uv, top)
    return root, XE


# ---------------------------------------------------------------- monitors
def box(name, x0, x1, y0, y1, z0, z1, mat, parent, bevel=0.0):
    """an axis-aligned box (mm, parent coordinates), optionally bevelled"""
    v = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    f = [[0, 2, 3, 1], [4, 5, 7, 6], [0, 1, 5, 4], [2, 6, 7, 3], [0, 4, 6, 2], [1, 3, 7, 5]]
    ob = mesh(name, v, f, mat, None, parent, smooth=0)
    if bevel:
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width = bevel
        m.segments = 4
        m.limit_method = "ANGLE"
        ob.modifiers.new("wn", "WEIGHTED_NORMAL")
        try:
            ob.data.shade_smooth()
        except AttributeError:
            pass
    return ob


def frustum(name, front, back, y0, y1, zc, mat, parent):
    """the tapered back of a CRT: a rectangle `front` (w, h) at y0 to `back`
    at y1, centred on x 0, z zc"""
    (fw, fh), (bw, bh) = front, back
    v = [(-fw / 2, y0, zc - fh / 2), (fw / 2, y0, zc - fh / 2), (fw / 2, y0, zc + fh / 2), (-fw / 2, y0, zc + fh / 2),
         (-bw / 2, y1, zc - bh / 2), (bw / 2, y1, zc - bh / 2), (bw / 2, y1, zc + bh / 2), (-bw / 2, y1, zc + bh / 2)]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    ob = mesh(name, v, f, mat, None, parent, smooth=0)
    m = ob.modifiers.new("bevel", "BEVEL")
    m.width = 8
    m.segments = 3
    return ob


class Screen:
    """an emissive screen showing an image: off (dark glass), switching on
    (`crt`: a bright line opening to the full picture; else a fade), on.
    set(t) with t the seconds since power on (< 0: off)"""

    def __init__(self, name, image, crt):
        self.crt = crt
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        out = nt.nodes["Material Output"]
        glass = nt.nodes["Principled BSDF"]
        glass.inputs["Base Color"].default_value = (0.006, 0.007, 0.008, 1)
        glass.inputs["Roughness"].default_value = 0.08 if crt else 0.25
        uv = nt.nodes.new("ShaderNodeTexCoord")
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(image)
        tex.interpolation = "Closest" if not crt else "Linear"
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(uv.outputs["UV"], sep.inputs["Vector"])
        # the visible band: |v - 0.5| < half
        sub = nt.nodes.new("ShaderNodeMath")
        sub.operation = "SUBTRACT"
        sub.inputs[1].default_value = 0.5
        nt.links.new(sep.outputs["Y"], sub.inputs[0])
        ab = nt.nodes.new("ShaderNodeMath")
        ab.operation = "ABSOLUTE"
        nt.links.new(sub.outputs[0], ab.inputs[0])
        lt = nt.nodes.new("ShaderNodeMath")
        lt.operation = "LESS_THAN"
        nt.links.new(ab.outputs[0], lt.inputs[0])
        self.half = lt.inputs[1]
        # the picture, squeezed into the band while it opens (CRT)
        mp = nt.nodes.new("ShaderNodeMapping")
        nt.links.new(uv.outputs["UV"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
        self.mapping = mp
        mul = nt.nodes.new("ShaderNodeMix")
        mul.data_type = "RGBA"
        mul.blend_type = "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        nt.links.new(tex.outputs["Color"], mul.inputs["A"])
        nt.links.new(lt.outputs[0], mul.inputs["B"])
        # a white flash while the line opens
        flash = nt.nodes.new("ShaderNodeMix")
        flash.data_type = "RGBA"
        nt.links.new(mul.outputs["Result"], flash.inputs["A"])
        nt.links.new(lt.outputs[0], flash.inputs["B"])
        self.flash = flash.inputs["Factor"]
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(flash.outputs["Result"], em.inputs["Color"])
        self.strength = em.inputs["Strength"]
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(glass.outputs["BSDF"], add.inputs[0])
        nt.links.new(em.outputs["Emission"], add.inputs[1])
        nt.links.new(add.outputs["Shader"], out.inputs["Surface"])
        self.material = m
        self.full = 2.2 if crt else 1.6       # emission strength when on
        self.set(-1)

    def set(self, t):
        if t < 0:
            self.strength.default_value = 0.0
            return
        if self.crt:
            k = min(t / 0.35, 1.0)                        # the line opens in 0.35 s
            half = 0.004 + 0.5 * (k * k * (3 - 2 * k))
            self.half.default_value = half
            sy = max(0.5 / half, 1.0)                     # picture squeezed in the band
            self.mapping.inputs["Scale"].default_value = (1, sy, 1)
            self.mapping.inputs["Location"].default_value = (0, 0.5 - 0.5 * sy, 0)
            self.flash.default_value = max(0.0, 1 - t / 0.5) * 0.8
            self.strength.default_value = self.full * (1.6 - 0.6 * k if t < 0.6 else 1.0)
        else:
            self.half.default_value = 0.51
            self.flash.default_value = 0.0
            self.strength.default_value = self.full * min(t / 0.5, 1.0)


def screen_mesh(name, w, h, bulge, mat, parent, y, zc):
    """a screen w x h (mm) facing +Y, at y, centre height zc; a CRT
    bulges towards the viewer (+Y) by `bulge`"""
    n = 16
    v, f, uv = [], [], []
    for j in range(n + 1):
        for i in range(n + 1):
            u, t = i / n, j / n
            x, z = (0.5 - u) * w, (t - 0.5) * h
            d = bulge * (1 - (2 * u - 1) ** 2) * (1 - (2 * t - 1) ** 2)
            v.append((x, y + d, zc + z))
            uv.append((u, t))
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            f.append([a, a + 1, a + n + 2, a + n + 1])
    return mesh(name, v, f, mat, uv, parent, smooth=1.0)


def build_crt(name, image, parent):
    """a period colour monitor, about 14": beige body, tapered back, the
    screen 4:3 facing +Y; origin on the table under the centre of its front"""
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    root.parent = parent
    body = plastic(name + "_body", "BDB6A6", 0.5)
    dark = plastic(name + "_bezel", "2A2826", 0.6)
    box(name + "_front", -185, 185, -70, 0, 0, 330, body, root, bevel=6)
    frustum(name + "_back", (330, 290), (200, 190), -70, -330, 175, body, root)
    box(name + "_recess", -150, 150, 0, 3, 55, 285, dark, root, bevel=4)
    box(name + "_foot", -150, 150, -250, -20, -0.01, 12, dark, root, bevel=3)
    sc = Screen(name + "_screen", image, crt=True)
    screen_mesh(name + "_glass", 270, 202, 7, sc.material, root, 3.5, 172)
    box(name + "_knobs", 95, 140, 1, 6, 22, 40, dark, root, bevel=2)
    return root, sc


def build_flat(name, image, parent):
    """a 24" flat monitor on its stand, the screen 16:9 facing +Y; origin on
    the table under the centre of its front"""
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    root.parent = parent
    black = plastic(name + "_body", "1C1D1F", 0.35)
    grey = plastic(name + "_stand", "3A3B3E", 0.4)
    zc = 330
    box(name + "_panel", -272, 272, -22, 0, zc - 162, zc + 162, black, root, bevel=4)
    box(name + "_neck", -35, 35, -95, -40, 20, zc, grey, root, bevel=5)
    box(name + "_arm", -35, 35, -60, -20, zc - 60, zc + 20, grey, root, bevel=5)
    box(name + "_base", -120, 120, -170, 30, 0, 12, grey, root, bevel=5)
    sc = Screen(name + "_screen", image, crt=False)
    screen_mesh(name + "_glass", 531, 299, 0, sc.material, root, 0.4, zc + 4)
    return root, sc


# ---------------------------------------------------------------- Commodore 64
C64 = {
    "case": "A0957F",            # the brown-beige breadbin
    # the keyboard: tools/keyboards/c64-breadbin-SA.blend (SA profile, from
    # SA-profile-keys-3D-models, c64-breadbin-SA.scad): two meshes, "Caps"
    # and "Legends" (the legends as raised geometry), metres, X to the right
    # of who types, Y from the rear edge of row 0 (0) to the front (-), Z up
    # from the base of the caps; key (0, 0) of the layout at x 0
    "kb_blend": "c64-breadbin-SA.blend",
    "key": "413C2C",             # dark brown keycaps (the colours of the .scad)
    "legend": "EAE6CA",          # cream legends
    "fn": "5E5C5A",              # dark grey function keys
    "fn_x": 320.0,               # in the .blend, x beyond this (mm): the f keys
    # the covers: models/c64-case.zip (four STL, top and bottom, left and
    # right, already in place among them); front at -y, the typist's left at
    # -x: turned 180 degrees and moved to the rear edge at y 0, floor at z 0
    "case_zip": os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "c64-case.zip"),
    "case_shift": (0.0, 103.0, 1.9),
    # key (0, 0) of the layout: its left edge (+X, on the left of who types)
    # and rear edge; the plane of the keyboard (the edge of the opening, z
    # at kb_y0, and its slope), the keycap tops above it
    "kb_x0": 189.5, "kb_y0": 76.5, "kb_z0": 68.5, "kb_slope": -0.12, "kb_rise": 4.0,
    # (kb_z0: the keys raised by 6 mm by hand in FreeCAD, C64-assembly.FCStd;
    # the function keys by 8, fn_dz more than the others)
    "fn_dz": 2.0,
    # the expansion port opening at the rear, right of who types: centre x, z
    "slot_cart_x": -122.5, "slot_z": 14.0,
    # the power LED hole in the top, right of who types
    "led_at": (-157.0, 32.0, 72.3),
    "crt_at": (235, -250, 0), "flat_at": (-245, -250, 0),
}


def build_c64(screens, keyboards):
    """the Commodore 64 (breadbin): the covers of models/c64-case.zip, the
    SA keyboard of c64-breadbin-SA.blend (caps and legends as geometry),
    a dark inside, the power LED"""
    import tempfile
    import zipfile
    root = bpy.data.objects.new("c64", None)
    bpy.context.scene.collection.objects.link(root)
    root.scale = (MM, MM, MM)
    c = C64
    case = plastic("c64_case", c["case"], 0.55)
    dark = plastic("c64_dark", "1A1714", 0.8)
    tmp = tempfile.mkdtemp(prefix="c64case")
    with zipfile.ZipFile(c["case_zip"]) as z:
        for n in sorted(z.namelist()):
            if n.lower().endswith(".stl"):
                ob = import_stl(z.extract(n, tmp), case, root, rot_z=180)
                ob.location = c["case_shift"]
    # the inside, dark, seen through the gaps between the keys and the ports
    box("c64_inside", -196, 196, 12, 196, 4, 40, dark, root)

    lay = json.load(open(os.path.join(screens, "c64-keys.json")))["keys"]
    fnl = json.load(open(os.path.join(screens, "c64-fn.json")))["keys"]
    tilt = Matrix.Rotation(math.atan(c["kb_slope"]), 4, "X")
    pivot_y = c["kb_y0"]
    pivot_z = c["kb_z0"] - 7.9 + c["kb_rise"]
    to_case = lambda x, y, z: tuple(tilt @ Vector((x, y - pivot_y, z)) + Vector((0, pivot_y, pivot_z)))
    # a dark floor under the keys, seen only between them
    xs = [c["kb_x0"] - (k[0] + k[2]) * U for k in lay + fnl] + [c["kb_x0"] - k[0] * U for k in lay + fnl]
    ys = [pivot_y + k[1] * U for k in lay + fnl] + [pivot_y + (k[1] + k[3]) * U for k in lay + fnl]
    fx0, fx1, fy0, fy1 = min(xs) - 5, max(xs) + 5, min(ys) - 5, max(ys) + 5
    mesh("c64_keybed", [to_case(fx0, fy0, -1), to_case(fx1, fy0, -1), to_case(fx1, fy1, -1), to_case(fx0, fy1, -1)],
         [[0, 1, 2, 3]], dark, None, root, smooth=0)
    # the keys: the caps and the legends of the .blend (only those two
    # objects; its camera, lights, floor and tray stay out), to mm, the f
    # keys raised by fn_dz, then turned half round (+X on the left of who
    # types, +Y to the front), key (0, 0) on kb_x0 / kb_y0, on the slope
    with bpy.data.libraries.load(os.path.join(keyboards, c["kb_blend"]), link=False) as (src, dst):
        dst.objects = ["Caps", "Legends"]
    place = (Matrix.Translation((0, pivot_y, pivot_z)) @ tilt
             @ Matrix.Translation((c["kb_x0"], 0, 0)) @ Matrix.Rotation(math.pi, 4, "Z"))
    mats = {"Caps": plastic("c64_keys", c["key"], 0.38), "Legends": plastic("c64_legends", c["legend"], 0.38)}
    fn_mat = plastic("c64_fn", c["fn"], 0.38)
    for ob in dst.objects:
        me = ob.data
        me.transform(ob.matrix_world)                    # (identity in the .blend)
        me.transform(Matrix.Scale(1000.0, 4))            # m -> mm
        fn = [v.co.x > c["fn_x"] for v in me.vertices]
        for v, f in zip(me.vertices, fn):
            if f:
                v.co.z += c["fn_dz"]
        me.transform(place)
        me.materials.clear()
        me.materials.append(mats[ob.name])
        if ob.name == "Caps":                            # the f keys: grey caps
            me.materials.append(fn_mat)
            for p in me.polygons:
                p.material_index = 1 if fn[p.vertices[0]] else 0
        ob.name = "c64_" + ob.name.lower()
        ob.matrix_world = Matrix.Identity(4)
        bpy.context.scene.collection.objects.link(ob)
        ob.parent = root

    # the power LED in its hole, front right of the top
    led = bpy.data.materials.new("c64_led")
    led.use_nodes = True
    lb = led.node_tree.nodes["Principled BSDF"]
    lb.inputs["Base Color"].default_value = (0.25, 0.01, 0.01, 1)
    lb.inputs["Emission Color"].default_value = (1.0, 0.05, 0.02, 1)
    lb.inputs["Emission Strength"].default_value = 0.0
    lx, ly, lz = c["led_at"]
    box("c64_led", lx - 3, lx + 3, ly - 3, ly + 3, lz - 4, lz - 0.6, led, root, bevel=1)
    c = dict(c)
    c["led"] = lb.inputs["Emission Strength"]
    return root, c

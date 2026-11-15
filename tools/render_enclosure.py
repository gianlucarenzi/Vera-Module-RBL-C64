# -*- coding: utf-8 -*-
"""Photorealistic render of the enclosure with Blender (Cycles): the boards
from their VRML (colours of the 3D models), the shells and the back panel
from the STL of tools/make_enclosure.py, brass standoffs, a light studio.

  blender -b -P tools/render_enclosure.py

Environment (all optional):
  RENDER_OUT      output PNG (enclosure/<name>-render.png)
  RENDER_NAME     enclosure name (VERA-<board>-enclosure, as make_enclosure.sh)
  RENDER_VARIANT  backpanel (default) or open
  RENDER_MODE     still (default), anim (the assembly, frames f*.png to
                  RENDER_FRAMES_DIR) or desk (the computer and the monitors,
                  frames d*.png; DESK_ASSETS, DESK_SCREENS, DESK_MACHINE)
  RENDER_POSE     still: open (top shell lifted, panel out) or closed
  RENDER_FPS, RENDER_SECONDS, RENDER_FRAMES (a-b)   anim: 24, 12, all
  RENDER_COLOR    case colour, sRGB hex (default E3D9C6, RAL 1013 Oyster white)
  RENDER_SAMPLES  Cycles samples (default 128), RENDER_RES  WxH (1920x1080)
  RENDER_LIGHT    multiplier of the light powers (default 1.0)
  RENDER_FLOOR    the table: oak (default), pine or grey
  RENDER_MASK     solder mask colour of a module VRML made from the STEP,
                  sRGB hex (default 1F4F36)
  HDMI_DIR        the VERA-HDMI-Expansion (default ../Vera-HDMI-Expansion)
  RENDER_WRL, RENDER_HDMI_WRL   the VRML of the module and of the HDMI board
                  (default images/*.wrl of each project)

The VRML is read by a small parser of its own (Transform, Group, Shape,
IndexedFaceSet, DEF/USE): the VRML importer is not part of Blender 4.x.
Each VRML is placed like the STEP in make_enclosure.py: its board (the
widest flat shape) on the KiCad outline from enclosure/board.json.
"""
import colorsys
import json
import math
import os
import re
import sys

import bpy
from mathutils import Matrix, Vector

env = os.environ.get
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(ROOT)
data = json.load(open("enclosure/board.json"))
T = data["thickness"]
STANDOFF = float(re.search(r"^STANDOFF = ([\d.]+)", open("tools/make_enclosure.py").read(), re.M).group(1))
NAME = env("RENDER_NAME") or "VERA-%s-enclosure" % os.path.basename(ROOT).replace("Vera-Module-", "")
VARIANT = env("RENDER_VARIANT", "backpanel")
POSE = env("RENDER_POSE", "open")
OUT = os.path.abspath(env("RENDER_OUT") or "enclosure/%s%s-render.png" % (NAME, "-backpanel" if VARIANT == "backpanel" else ""))
HDMI_DIR = env("HDMI_DIR") or os.path.join(ROOT, "..", "Vera-HDMI-Expansion")
MM = 0.001                      # scene in metres, data in mm


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


# ---------------------------------------------------------------- VRML
TOKEN = re.compile(r'"[^"]*"|[{}\[\]]|[^\s,{}\[\]"#]+|#[^\n]*')
NUM = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")


class Parser:
    def __init__(self, text):
        self.toks = [t for t in TOKEN.findall(text) if not t.startswith("#")]
        self.i = 0
        self.defs = {}

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def node(self):
        t = self.next()
        if t == "USE":
            return self.defs.get(self.next())
        name = None
        if t == "DEF":
            name = self.next()
            t = self.next()
        if t == "NULL":
            return None
        n = {"type": t, "f": {}}
        if name:
            self.defs[name] = n
        assert self.next() == "{", "expected { after " + t
        while self.peek() != "}":
            field = self.next()
            if field in ("ROUTE", "PROTO", "EXTERNPROTO"):
                raise ValueError("unsupported VRML: " + field)
            n["f"][field] = self.value()
        self.next()
        return n

    def value(self):
        t = self.peek()
        if t == "[":
            self.next()
            if self.peek() == "]":
                self.next()
                return []
            if NUM.match(self.peek()):
                vals = []
                while self.peek() != "]":
                    vals.append(float(self.next()))
                self.next()
                return vals
            items = []
            while self.peek() != "]":
                items.append(self.node())
            self.next()
            return items
        if NUM.match(t):
            vals = []
            while self.peek() is not None and NUM.match(self.peek()):
                vals.append(float(self.next()))
            return vals
        if t in ("TRUE", "FALSE") or t.startswith('"'):
            return self.next()
        return self.node()

    def scene(self):
        nodes = []
        while self.peek() is not None:
            nodes.append(self.node())
        return nodes


def children(n):
    c = n["f"].get("children", [])
    return c if isinstance(c, list) else [c]


def transform(n):
    f = n["f"]
    t = Vector(f.get("translation", [0, 0, 0]))
    c = Vector(f.get("center", [0, 0, 0]))
    r = f.get("rotation", [0, 0, 1, 0])
    s = f.get("scale", [1, 1, 1])
    return (Matrix.Translation(t) @ Matrix.Translation(c) @ Matrix.Rotation(r[3], 4, Vector(r[:3]))
            @ Matrix.Diagonal((s[0], s[1], s[2], 1)) @ Matrix.Translation(-c))


def read_vrml(path):
    """[(material key, vertices, faces)] in file units, transforms applied"""
    shapes = []

    def walk(n, m):
        if n is None:
            return
        if n["type"] == "Transform":
            m = m @ transform(n)
        if n["type"] in ("Transform", "Group", "Collision", "Anchor", "Billboard"):
            for c in children(n):
                walk(c, m)
        elif n["type"] == "Shape":
            g = n["f"].get("geometry")
            if not g or g["type"] != "IndexedFaceSet" or not g["f"].get("coord"):
                return
            mat = ((n["f"].get("appearance") or {"f": {}})["f"].get("material") or {"f": {}})["f"]
            key = (tuple(round(x, 3) for x in mat.get("diffuseColor", [0.8, 0.8, 0.8])),
                   round(mat.get("shininess", [0.2])[0], 2), round(mat.get("transparency", [0])[0], 2))
            p = g["f"]["coord"]["f"]["point"]
            verts = [tuple(m @ Vector(p[i:i + 3])) for i in range(0, len(p) - 2, 3)]
            faces, cur = [], []
            for k in g["f"].get("coordIndex", []):
                k = int(k)
                if k < 0:
                    if len(cur) >= 3:
                        faces.append(cur)
                    cur = []
                else:
                    cur.append(k)
            if len(cur) >= 3:
                faces.append(cur)
            if faces:
                shapes.append((key, verts, faces))

    for n in Parser(open(path, encoding="utf-8", errors="replace").read()).scene():
        walk(n, Matrix.Identity(4))
    return shapes


def bbox(verts):
    xs, ys, zs = zip(*verts)
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def place_board(shapes, outline, z0):
    """scale and move the VRML so its board lies on the KiCad outline (case
    coordinates: X = KiCad x, Y = -KiCad y) with its bottom at z0"""
    boxes = [bbox(v) for k, v, f in shapes]
    area = [(b[1] - b[0]) * (b[3] - b[2]) for b in boxes]
    big = max(area)
    # the board body: the thickest of the widest shapes (not a mask layer)
    i = max((j for j in range(len(shapes)) if area[j] > 0.98 * big), key=lambda j: boxes[j][5] - boxes[j][4])
    b = boxes[i]
    xs = [p[0] for p in outline]
    ys = [-p[1] for p in outline]
    s = (max(xs) - min(xs)) / (b[1] - b[0])
    off = Vector((min(xs) - b[0] * s, min(ys) - b[2] * s, z0 - b[4] * s))
    out = [(k, [tuple((Vector(p) * s + off) * MM) for p in v], f) for k, v, f in shapes]
    return out, i


# ---------------------------------------------------------------- materials
def principled(name, rgb, rough, metal=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = rgb + (1,)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
    return m


def vrml_material(key, cache={}):
    """KiCad/FreeCAD colours to PBR: greys and golds that look like metal
    become metal, the solder mask glossy, the rest plastic"""
    if key in cache:
        return cache[key]
    rgb, shin, tr = key
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    lin = tuple(srgb_to_linear(c) for c in rgb)
    if s < 0.10 and 0.55 < v < 0.86:
        m = principled("metal", lin, 0.28, 1.0)                 # tin, nickel shells
    elif 0.07 < h < 0.17 and s > 0.35 and v > 0.6:
        m = principled("gold", lin, 0.22, 1.0)                  # gold fingers, pins
    elif 0.2 < h < 0.5 and s > 0.3:
        m = principled("mask", lin, 0.25, 0.0)                  # solder mask
    else:
        m = principled("plastic", lin, 0.45 if v > 0.3 else 0.35, 0.0, 1 - tr)
    cache[key] = m
    return m


def case_material(name, rgb, axis):
    """matte FDM plastic with faint 0.2 mm layer lines along `axis`"""
    m = principled(name, rgb, 0.55)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = axis
    wave.inputs["Scale"].default_value = 2 * math.pi / (20 * 0.0002)    # 0.2 mm period
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.00004
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


# ---------------------------------------------------------------- objects
def mesh_object(name, verts, faces, mat, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(mat)
    if smooth:
        smooth_by_angle(ob)
    return ob


def smooth_by_angle(ob, angle=0.6):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=angle)      # Blender 4.1+
    except Exception:
        bpy.ops.object.shade_smooth()
        ob.data.use_auto_smooth = True
        ob.data.auto_smooth_angle = angle


def board_objects(name, shapes):
    """one object per material, so a big board stays a few objects"""
    groups = {}
    for key, v, f in shapes:
        g = groups.setdefault(key, ([], []))
        base = len(g[0])
        g[0].extend(v)
        g[1].extend([[base + k for k in face] for face in f])
    obs = []
    for j, (key, (v, f)) in enumerate(groups.items()):
        obs.append(mesh_object("%s_%d" % (name, j), v, f, vrml_material(key)))
    return obs


def import_stl(path, mat):
    before = set(bpy.data.objects)
    try:
        bpy.ops.wm.stl_import(filepath=path, global_scale=MM)       # Blender 4.1+
    except AttributeError:
        bpy.ops.import_mesh.stl(filepath=path, global_scale=MM)
    ob = (set(bpy.data.objects) - before).pop()
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    smooth_by_angle(ob, 0.5)
    return ob


def hex_prism(x, y, z0, z1, across_flats, mat, name):
    r = across_flats / 2 / math.cos(math.pi / 6)
    ring = [(x + r * math.cos(math.pi / 6 + k * math.pi / 3), y + r * math.sin(math.pi / 6 + k * math.pi / 3)) for k in range(6)]
    verts = [(px * MM, py * MM, z0 * MM) for px, py in ring] + [(px * MM, py * MM, z1 * MM) for px, py in ring]
    faces = [list(range(5, -1, -1)), list(range(6, 12))] + [[k, (k + 1) % 6, 6 + (k + 1) % 6, 6 + k] for k in range(6)]
    return mesh_object(name, verts, faces, mat, smooth=False)


# ---------------------------------------------------------------- scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

print("reading the board VRML")
WRL = env("RENDER_WRL") or "images/VERA-MODULE-RBL.wrl"
board, pcb = place_board(read_vrml(WRL), data["outline"], 0.0)
if "step2wrl" in open(WRL, errors="replace").read(400):
    # a VRML made from the STEP (no kicad-cli) has a flat light green board,
    # in more than one shape: the solder mask colour of the KiCad VRML
    # instead (RENDER_MASK, sRGB hex)
    mask = env("RENDER_MASK", "1F4F36")
    green = tuple(int(mask[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    pcb_key = board[pcb][0]
    board = [((green, 0.9, 0.0),) + b[1:] if b[0] == pcb_key else b for b in board]
board_obs = board_objects("board", board)
hdmi_obs = []
hdmi_wrl = env("RENDER_HDMI_WRL") or os.path.join(HDMI_DIR, "images", "VERA-HDMI-Expansion.wrl")
if "hdmi" in data and os.path.isfile(hdmi_wrl):
    print("reading the HDMI VRML")
    hdmi, _ = place_board(read_vrml(hdmi_wrl), data["hdmi"]["outline"], T + STANDOFF)
    hdmi_obs = board_objects("hdmi", hdmi)
else:
    print("no VERA-HDMI-Expansion VRML in", HDMI_DIR)

case_rgb = hex_rgb(env("RENDER_COLOR", "E3D9C6"))
mat_z = case_material("case", case_rgb, "Z")         # shells: layers along Z
mat_y = case_material("panel", case_rgb, "Y")        # panel printed on its flange
prefix = "enclosure/%s%s" % (NAME, "-backpanel" if VARIANT == "backpanel" else "")
bottom = import_stl(prefix + "-bottom.stl", mat_z)
top = import_stl(prefix + "-top.stl", mat_z)
panel = import_stl(prefix + "-panel.stl", mat_y) if VARIANT == "backpanel" else None

brass = principled("brass", hex_rgb("C9A44C"), 0.3, 1.0)
standoffs = [hex_prism(h[0], -h[1], T, T + STANDOFF, 5.5, brass, "standoff%d" % k)
             for k, h in enumerate(data["holes"])]


def world_box(obs):
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in obs for c in o.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


# the closed enclosure: floor, lights and the centre of the camera moves (the
# boards are inside it, and a VRML may carry stray parts far from its board)
shells = [o for o in (bottom, top, panel) if o is not None]
lo, hi = world_box(shells)
centre = (lo + hi) / 2

def wood_material(kind):
    """procedural wood for the table: grain along X (rings of a Wave texture
    bent by noise), two tones, varnish-like roughness, a faint relief"""
    tones = {"oak": ("6E4A2C", "A47A50", 0.0070),       # dark, light, grain period (m)
             "pine": ("B8834E", "E2BC86", 0.0110)}
    dark, light, period = tones[kind]
    m = principled("wood_" + kind, hex_rgb(light), 0.42)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.04, 1.0, 1.0)  # long, straight grain along X
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.0
    noise.inputs["Detail"].default_value = 4.0
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Y"
    wave.inputs["Scale"].default_value = 2 * math.pi / (20 * period)
    wave.inputs["Distortion"].default_value = 0.8
    wave.inputs["Detail"].default_value = 2.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = hex_rgb(dark) + (1,)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = hex_rgb(light) + (1,)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.05
    bump.inputs["Distance"].default_value = 0.0002
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Color"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


bpy.ops.mesh.primitive_plane_add(size=40, location=(centre.x, centre.y, lo.z))
floor = bpy.context.active_object
FLOOR = env("RENDER_FLOOR", "oak")
floor.data.materials.append(wood_material(FLOOR) if FLOOR in ("oak", "pine")
                            else principled("floor", (0.55, 0.55, 0.56), 0.6))

world = bpy.data.worlds.new("studio")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.60, 0.61, 0.63, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.12


def area_light(name, power, size, direction, dist):
    d = Vector(direction).normalized()
    li = bpy.data.lights.new(name, "AREA")
    li.energy = power
    li.size = size
    ob = bpy.data.objects.new(name, li)
    scene.collection.objects.link(ob)
    ob.location = centre + d * dist
    ob.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    return ob


# far and large lights (even light, soft shadows) for a subject of about
# 15 cm: about 3/4 of the light of 0.8 m and 14 W for the key (W)
LIGHT = float(env("RENDER_LIGHT", "1.0"))
area_light("key", 42 * LIGHT, 1.2, (0.8, 0.5, 1.0), 1.6)
area_light("fill", 15 * LIGHT, 2.0, (-0.9, 0.7, 0.5), 1.8)
area_light("rim", 27 * LIGHT, 1.0, (-0.3, -1.0, 0.8), 1.6)

# ---------------------------------------------------------------- camera
cam = bpy.data.cameras.new("cam")
cam.lens = 70
cam.sensor_width = 36
cam_ob = bpy.data.objects.new("cam", cam)
scene.collection.objects.link(cam_ob)
scene.camera = cam_ob
cam.clip_start = 0.01
cam.clip_end = 20
cam.dof.use_dof = True
cam.dof.aperture_fstop = 11
w, h = (int(x) for x in env("RENDER_RES", "1920x1080").split("x"))
MARGIN = 1.12


def aim(direction, box):
    """camera on `direction` from the centre of `box`, at the distance that
    fits the box projected on the image plane"""
    d = Vector(direction).normalized()
    blo, bhi = box
    c = (blo + bhi) / 2
    right = Vector((0, 0, 1)).cross(d).normalized()
    up = d.cross(right)
    corners = [Vector((x, y, z)) for x in (blo.x, bhi.x) for y in (blo.y, bhi.y) for z in (blo.z, bhi.z)]
    half_w = max(abs((p - c).dot(right)) for p in corners)
    half_h = max(abs((p - c).dot(up)) for p in corners)
    depth = max((p - c).dot(d) for p in corners)
    tan_w = cam.sensor_width / 2 / cam.lens
    tan_h = tan_w * h / w
    cam_ob.location = c + d * (max(half_w / tan_w, half_h / tan_h) * MARGIN + depth)
    cam_ob.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.dof.focus_distance = (cam_ob.location - c).length


# ---------------------------------------------------------------- render settings
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = int(env("RENDER_SAMPLES", "128"))
try:
    import _cycles
    oidn = _cycles.with_openimagedenoise
except (ImportError, AttributeError):
    oidn = False
if oidn:
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
else:
    # a Blender without the denoiser (e.g. Debian's): more samples instead
    scene.cycles.use_denoising = False
    scene.cycles.samples *= 4
    print("no OpenImageDenoise in this Blender: %d samples, no denoiser" % scene.cycles.samples)
scene.render.resolution_x, scene.render.resolution_y = w, h
scene.render.resolution_percentage = 100
try:
    scene.view_settings.view_transform = "AgX"
except TypeError:
    scene.view_settings.view_transform = "Filmic"
scene.render.image_settings.file_format = "PNG"

PORT_SIDE = Vector((0.55, 0.65, 0.52))      # three quarters from the port side, above

if env("RENDER_MODE", "still") == "still":
    if POSE == "open":
        top.location.z += 45 * MM
        if panel:
            panel.location.y += 30 * MM
    aim(PORT_SIDE, world_box(shells))
    scene.render.filepath = OUT
    print("rendering %dx%d, %d samples, to %s" % (w, h, scene.cycles.samples, OUT))
    bpy.ops.render.render(write_still=True)
    print("written", OUT)
    sys.exit(0)

def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3                 # fast in, slow at the end


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- desk
# The second part of the video (RENDER_MODE=desk, frames d0001.png ...): the
# closed enclosure on the table, the computer (tools/desk_scene.py) slides in
# behind it until its edge connector takes the module's fingers, seen from
# behind; then a cut to the front, from above: the computer with two monitors
# behind it, which switch on: the left one (CRT) on the computer's own video,
# BASIC, the right one (flat, HDMI) on the VERA, its 256 colours.
if env("RENDER_MODE", "still") == "desk":
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import desk_scene

    FPS = int(env("RENDER_FPS", "24"))
    SECONDS = float(env("RENDER_SECONDS", "10.5"))
    TOTAL = int(round(FPS * SECONDS))
    first, last = (int(x) for x in env("RENDER_FRAMES", "1-%d" % TOTAL).split("-"))
    FRAMES_DIR = os.path.abspath(env("RENDER_FRAMES_DIR", "frames"))
    os.makedirs(FRAMES_DIR, exist_ok=True)
    SCREENS = os.path.abspath(env("DESK_SCREENS", "screens"))
    MACHINE = env("DESK_MACHINE") or ("c64" if "C64" in NAME else "xe")

    # the module's edge fingers: the outline points with the largest KiCad y,
    # its widest segment (the cartridge / expansion port fingers)
    ymax = max(p[1] for p in data["outline"])
    xs_f = sorted(p[0] for p in data["outline"] if p[1] > ymax - 0.01)
    segs = [(xs_f[i], xs_f[i + 1]) for i in range(0, len(xs_f) - 1, 2)]
    fx0, fx1 = max(segs, key=lambda s: s[1] - s[0])
    finger = Vector(((fx0 + fx1) / 2, -ymax, 0))

    if MACHINE == "xe":
        comp, info = desk_scene.build_xe(env("DESK_ASSETS"), SCREENS, os.path.join(ROOT, "tools", "keyboards"))
        left_img = os.path.join(SCREENS, "atari-basic.png")
    else:
        comp, info = desk_scene.build_c64(SCREENS, os.path.join(ROOT, "tools", "keyboards"))
        left_img = os.path.join(SCREENS, "c64-basic.png")

    # computer coordinates (mm, rear at y 0, front +Y) to the world: turned
    # half round (its rear faces the fingers), its slot on the fingers (the
    # fingers INSERT mm inside), its table on the enclosure's
    INSERT = 8.0
    turn = Matrix.Rotation(math.pi, 4, "Z")
    shift = Vector((finger.x + info["slot_cart_x"], finger.y + INSERT, lo.z / MM))
    def to_world(p):
        return (turn @ Vector(p) + shift) * MM

    desk = bpy.data.objects.new("desk", None)
    scene.collection.objects.link(desk)
    desk.rotation_euler = (0, 0, math.pi)
    desk.location = shift * MM
    desk.scale = (MM, MM, MM)
    comp.scale = (1, 1, 1)
    comp.parent = desk
    crt, crt_screen = desk_scene.build_crt("crt", left_img, desk)
    crt.location = info.get("crt_at", (225, -250, 0))
    flat, flat_screen = desk_scene.build_flat("flat", os.path.join(SCREENS, "vera-256-wide.png"), desk)
    flat.location = info.get("flat_at", (-240, -250, 0))

    def wbox(lo_, hi_):
        pts = [to_world((x, y, z)) for x in (lo_[0], hi_[0]) for y in (lo_[1], hi_[1]) for z in (lo_[2], hi_[2])]
        return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
                Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))

    # the lights of a scene about 1 m wide, centred on the desk
    for o in [o for o in scene.objects if o.type == "LIGHT"]:
        bpy.data.objects.remove(o)
    centre = to_world((0, -150, 120))
    DL = float(env("DESK_LIGHT", "1.0")) * LIGHT
    area_light("key", 110 * DL, 2.0, (-0.6, -1.0, 1.1), 2.6)
    area_light("fill", 40 * DL, 2.5, (0.9, -0.5, 0.6), 2.8)
    area_light("rim", 60 * DL, 1.6, (0.2, 1.0, 0.8), 2.6)
    cam.dof.aperture_fstop = 16

    SLIDE = (0.6, 3.2)                  # the computer comes from 160 mm away
    CUT = 4.2                           # to the front view
    ON_LEFT, ON_RIGHT = 5.2, 6.3        # the monitors switch on
    sx_ = info["slot_cart_x"]           # the side view, centred on the slot
    rear_box = wbox((sx_ - 150, -175, 0), (sx_ + 150, 60, 50))
    front_box = wbox((-420, -260, 0), (380, 235, 500))

    def turn_dir(d, deg):
        return Matrix.Rotation(math.radians(deg), 3, "Z") @ Vector(d)

    def pose_desk(t):
        k = ease((t - SLIDE[0]) / (SLIDE[1] - SLIDE[0]))
        comp.location = (0, 160 * (1 - k), 0)          # computer coordinates: towards its front
        crt_screen.set(t - ON_LEFT)
        if "led" in info:                              # the power LED, with the computer
            info["led"].default_value = 6.0 if t >= ON_LEFT - 0.5 else 0.0
        flat_screen.set(t - ON_RIGHT)
        if t < CUT:
            s = smooth(t / CUT)
            # behind the computer, on the side of its right hand, slowly turning
            d = turn @ turn_dir((-1.0, -0.2, 0.5), -10 * s)
            aim(d, rear_box)
        else:
            s = smooth((t - CUT) / (SECONDS - CUT))
            d = turn @ turn_dir((0.12, 1.0, 0.62), 5 * s)
            global MARGIN
            MARGIN = 1.0 - 0.07 * s
            aim(d, front_box)

    print("desk: frames %d-%d of %d (%d fps), %dx%d, %d samples, to %s" % (
        first, last, TOTAL, FPS, w, h, scene.cycles.samples, FRAMES_DIR))
    for f in range(first, last + 1):
        pose_desk((f - 1) / FPS)
        scene.render.filepath = os.path.join(FRAMES_DIR, "d%04d.png" % f)
        bpy.ops.render.render(write_still=True)
        print("frame", f, "written")
    sys.exit(0)

# ---------------------------------------------------------------- animation
# The assembly as in the GIF (tools/enclosure_assembly.py): every part comes
# from its exploded place, one after the other, while the camera turns
# around the enclosure, comes closer and ends on the port side. Frames f0001.png ... of the range
# RENDER_FRAMES (a-b, 1-based) of RENDER_SECONDS at RENDER_FPS, so a long
# animation can be split over many machines.
FPS = int(env("RENDER_FPS", "24"))
SECONDS = float(env("RENDER_SECONDS", "12"))
TOTAL = int(round(FPS * SECONDS))
first, last = (int(x) for x in env("RENDER_FRAMES", "1-%d" % TOTAL).split("-"))
FRAMES_DIR = os.path.abspath(env("RENDER_FRAMES_DIR", "frames"))
os.makedirs(FRAMES_DIR, exist_ok=True)

# (objects, exploded offset in mm, start s, end s)
groups = [(board_obs, (0, 0, 70), 0.6, 2.2),
          (standoffs, (0, 0, 50), 1.8, 3.0),
          (hdmi_obs, (0, 0, 90), 2.6, 4.2),
          ([top], (0, 0, 120), 4.0, 5.8)]
if panel:
    groups.append(([panel], (0, 60, 0), 5.6, 7.2))
home = {o.name: o.location.copy() for g in groups for o in g[0]}
# boxes of the moving groups, closed, for the framing: the boards as the
# space they fill inside the case (a VRML may carry stray parts)
inner = lambda z0, z1: (Vector((lo.x, lo.y, z0 * MM)), Vector((hi.x, hi.y, z1 * MM)))
gbox = [inner(0, T + 10), world_box(standoffs), inner(T + STANDOFF, T + STANDOFF + 12), world_box([top])]
if panel:
    gbox.append(world_box([panel]))


def pose(t):
    """parts and camera at time t (s)"""
    blo, bhi = Vector(lo), Vector(hi)
    for (obs, off, t0, t1), (glo, ghi) in zip(groups, gbox):
        k = 1 - ease((t - t0) / (t1 - t0))
        d = Vector(off) * MM * k
        for o in obs:
            o.location = home[o.name] + d
        for c in (glo + d, ghi + d):
            blo = Vector((min(blo.x, c.x), min(blo.y, c.y), min(blo.z, c.z)))
            bhi = Vector((max(bhi.x, c.x), max(bhi.y, c.y), max(bhi.z, c.z)))
    # half a turn around, coming lower, ending three quarters on the port side
    s = smooth(t / SECONDS)
    az = math.atan2(PORT_SIDE.y, PORT_SIDE.x) + math.radians(150) * (1 - s)
    el = math.radians(36 - 14 * s)
    aim((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)), (blo, bhi))


print("rendering frames %d-%d of %d (%d fps), %dx%d, %d samples, to %s" % (
    first, last, TOTAL, FPS, w, h, scene.cycles.samples, FRAMES_DIR))
for f in range(first, last + 1):
    pose((f - 1) / FPS)
    scene.render.filepath = os.path.join(FRAMES_DIR, "f%04d.png" % f)
    bpy.ops.render.render(write_still=True)
    print("frame", f, "written")

# Blender (blender -b -P tools/fc_context.py, from the repository root, with
# the environment of tools/render_enclosure.py in desk mode): runs the desk
# scene without rendering and, at the first frame asked for, writes in $CTX_OUT
# the computer's meshes (computer coordinates, mm: rear edge at y 0, front
# +Y, table z 0) as binary STL, and placement.json (the module of the teaser:
# enclosure coordinates -> computer, the fingers, the holes, the meshes and
# their colours). For tools/fc_assembly.sh.
import bpy, os, struct, json
from mathutils import Matrix, Vector
OUT = os.environ["CTX_OUT"]
os.makedirs(OUT, exist_ok=True)
def write_stl(path, tris):
    with open(path, "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(tris)))
        for a, b, c in tris:
            n = (b - a).cross(c - a)
            n = n.normalized() if n.length else n
            f.write(struct.pack("<12fH", *n, *a, *b, *c, 0))

def legend_tris(o, me, m, step=2):
    """the legends of a texture (alpha) mapped by UV on a mesh, as geometry:
    the texture's opaque pixels (every `step`-th, in horizontal runs) as
    quads on the up-facing triangles of the mesh (computer coordinates,
    0.15 mm above); returns (triangles, legend colour) or (None, None)"""
    mat = o.material_slots[0].material if o.material_slots else None
    tex = [n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE"] if mat and mat.node_tree else []
    if not tex or not me.uv_layers:
        return None, None
    img = tex[0].image
    W, H = img.size
    px = img.pixels[:]
    uvl = me.uv_layers.active.data
    # up-facing triangles, indexed on a UV grid
    G = 400
    grid = {}
    tri = []
    for t in me.loop_triangles:
        P = [m @ me.vertices[i].co for i in t.vertices]
        n = (P[1] - P[0]).cross(P[2] - P[0])
        if n.length == 0 or abs(n.normalized().z) < 0.6:    # either winding
            continue
        UV = [uvl[li].uv.copy() for li in t.loops]
        k = len(tri)
        tri.append((P, UV, Vector((0, 0, 1))))
        u0, u1 = min(q.x for q in UV), max(q.x for q in UV)
        v0, v1 = min(q.y for q in UV), max(q.y for q in UV)
        for gx in range(int(u0 * G), int(u1 * G) + 1):
            for gy in range(int(v0 * G), int(v1 * G) + 1):
                grid.setdefault((gx, gy), []).append(k)

    def at(u, v):
        best = None
        for k in grid.get((int(u * G), int(v * G)), ()):
            P, UV, n = tri[k]
            a, b, c = UV
            d = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y)
            if abs(d) < 1e-14:
                continue
            l1 = ((b.y - c.y) * (u - c.x) + (c.x - b.x) * (v - c.y)) / d
            l2 = ((c.y - a.y) * (u - c.x) + (a.x - c.x) * (v - c.y)) / d
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) < -1e-4:
                continue
            q = P[0] * l1 + P[1] * l2 + P[2] * l3 + n * 0.15
            if best is None or q.z > best.z:
                best = q
        return best

    out, col, cn = [], [0.0, 0.0, 0.0], 0
    for y in range(0, H, step):
        row = y * W * 4
        x = 0
        while x < W:
            if px[row + x * 4 + 3] < 0.5:
                x += step
                continue
            x0 = x
            while x < W and px[row + x * 4 + 3] >= 0.5:
                if cn < 20000:
                    for i in range(3):
                        col[i] += px[row + x * 4 + i]
                    cn += 1
                x += step
            # image row 0 is the bottom (v 0) in Blender
            u0, u1 = x0 / W, x / W
            v0, v1 = y / H, (y + step) / H
            c = [at(u0, v0), at(u1, v0), at(u1, v1), at(u0, v1)]
            if all(c):
                out += [(c[0], c[1], c[2]), (c[0], c[2], c[3])]
    if not out:
        return None, None
    rgb = [round((v / cn) ** (1 / 2.2), 3) for v in col]
    return out, rgb


def probe(*a, **k):
    g = PROBE.g
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    root = next(o for o in bpy.data.objects if o.name in ("atari130xe", "c64"))
    inv = root.matrix_world.inverted()
    def desc(o):
        for c in o.children:
            yield c
            yield from desc(c)
    parts = {}
    for o in desc(root):
        if o.type != "MESH" or o.hide_render:
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        m = inv @ o.matrix_world
        me.calc_loop_triangles()
        tris = [tuple(m @ me.vertices[i].co for i in t.vertices) for t in me.loop_triangles]
        # textured legends (the XE keys) as geometry, for FreeCAD
        lt, lrgb = legend_tris(o, me, m)
        if lt:
            lname = o.name.replace(" ", "_").replace(".", "_") + "_legends"
            write_stl(os.path.join(OUT, lname + ".stl"), lt)
            parts[lname] = {"material": "legends", "tris": len(lt), "rgb": lrgb, "bbox": [[0, 0, 0], [0, 0, 0]]}
        ev.to_mesh_clear()
        mat = o.material_slots[0].material.name if o.material_slots and o.material_slots[0].material else ""
        name = o.name.replace(" ", "_").replace(".", "_")
        write_stl(os.path.join(OUT, name + ".stl"), tris)
        bb = [min(p[i] for t in tris for p in t) for i in range(3)], [max(p[i] for t in tris for p in t) for i in range(3)]
        parts[name] = {"material": mat, "tris": len(tris), "bbox": [[round(x, 1) for x in bb[0]], [round(x, 1) for x in bb[1]]]}
        # colour from the material (sRGB-ish from the linear base colour)
        try:
            bc = o.material_slots[0].material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value
            parts[name]["rgb"] = [round((c ** (1 / 2.2)), 3) for c in bc[:3]]
        except Exception:
            pass
    # the module: an enclosure-coordinate point w (mm) is at world
    # w*MM + offset (offset: the lift and the slide, the same for every part)
    shells = [o for o in bpy.data.objects if o.type == "MESH" and "enclosure" in o.name]
    off = shells[0].matrix_world.translation.copy()
    A = inv
    t = A @ off                                   # w = 0
    R = (A @ Matrix.Translation(off)).to_3x3() * 1e-3   # (to mm per mm)
    R = Matrix([[round(R[i][j], 6) for j in range(3)] for i in range(3)])
    finger = g["finger"]
    json.dump({"machine": g["MACHINE"], "insert": g["INSERT"], "lift": g["LIFT"],
               "module_rotation": [list(r) for r in R], "module_translation": list(t),
               "finger": list(finger), "thickness": g["T"], "standoff": g["STANDOFF"],
               "holes": g["data"]["holes"], "parts": parts},
              open(os.path.join(OUT, "placement.json"), "w"), indent=1)
    print("CTX", g["MACHINE"], "R", [list(r) for r in R], "t", list(t), len(parts), "parts")
    raise SystemExit(0)
class _P: pass
PROBE = probe
src = open(os.path.join(os.getcwd(), "tools", "render_enclosure.py")).read()
src = src.replace("bpy.ops.render.render(write_still=True)", "PROBE()")
g = {"__name__": "__main__", "__file__": os.path.join(os.getcwd(), "tools", "render_enclosure.py"), "PROBE": probe}
probe.g = g
PROBE.g = g
try:
    exec(compile(src, g["__file__"], "exec"), g)
except SystemExit:
    pass

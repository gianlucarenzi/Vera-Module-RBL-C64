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

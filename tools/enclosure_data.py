#!/usr/bin/env python3
"""Board data for tools/make_enclosure.py, read from the KiCad 5 PCB.

Writes a JSON file with, in KiCad millimetres (y grows downwards):
  - outline: the Edge.Cuts loop as a polygon (arcs split in short segments)
  - thickness: board thickness
  - holes: the M3 mounting holes (H*)
  - parts: centre and size of the parts the enclosure cares about (U7 ESP32,
    U2 FPGA, SW1 RESET, SW3 BOOT0)
  - port_parts: the connectors on the port side (footprint boxes)
  - hdmi: the VERA-HDMI-Expansion board, if its PCB is given: outline and
    offset that puts its mounting holes on the holes of this board

usage: ./run_pcbnew.sh tools/enclosure_data.py BOARD.kicad_pcb OUT.json [HDMI.kicad_pcb]
"""
import json
import math
import sys

import pcbnew

MM = pcbnew.ToMM


def outline(board):
    """Edge.Cuts as one closed polygon (list of [x, y])."""
    segs = []
    for d in board.GetDrawings():
        if d.GetLayerName() != "Edge.Cuts":
            continue
        if d.GetShape() == pcbnew.S_ARC:
            c = d.GetCenter()
            s = d.GetArcStart()
            ang = d.GetAngle() / 10.0          # tenths of degree, CW in KiCad y-down
            r = math.hypot(MM(s.x) - MM(c.x), MM(s.y) - MM(c.y))
            a0 = math.atan2(MM(s.y) - MM(c.y), MM(s.x) - MM(c.x))
            n = max(2, int(abs(ang) / 10) + 1)
            pts = [(MM(c.x) + r * math.cos(a0 + math.radians(ang) * k / n),
                    MM(c.y) + r * math.sin(a0 + math.radians(ang) * k / n)) for k in range(n + 1)]
        else:
            s, e = d.GetStart(), d.GetEnd()
            pts = [(MM(s.x), MM(s.y)), (MM(e.x), MM(e.y))]
        if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 1e-4:
            segs.append(pts)
    # chain the segments into a loop
    loop = list(segs.pop(0))
    while segs:
        end = loop[-1]
        best = min(range(len(segs)), key=lambda i: min(math.hypot(segs[i][0][0] - end[0], segs[i][0][1] - end[1]),
                                                       math.hypot(segs[i][-1][0] - end[0], segs[i][-1][1] - end[1])))
        s = segs.pop(best)
        if math.hypot(s[0][0] - end[0], s[0][1] - end[1]) > math.hypot(s[-1][0] - end[0], s[-1][1] - end[1]):
            s = s[::-1]
        loop.extend(s[1:])
    if math.hypot(loop[0][0] - loop[-1][0], loop[0][1] - loop[-1][1]) < 1e-3:
        loop.pop()
    return [[round(x, 4), round(y, 4)] for x, y in loop]


def footprints(board):
    out = {}
    for m in board.GetModules():
        r = m.GetFootprintRect()
        out[m.GetReference()] = dict(
            x=MM(m.GetPosition().x), y=MM(m.GetPosition().y), back=m.IsFlipped(),
            w=MM(r.GetWidth()), h=MM(r.GetHeight()), fp=str(m.GetFPID().GetLibItemName()),
            x0=MM(r.GetX()), x1=MM(r.GetRight()), y0=MM(r.GetY()), y1=MM(r.GetBottom()))
    return out


def holes(fps):
    return sorted([[v["x"], v["y"]] for k, v in fps.items() if k.startswith("H") and "MountingHole" in v["fp"]])


def main():
    b = pcbnew.LoadBoard(sys.argv[1])
    fps = footprints(b)
    data = dict(outline=outline(b), thickness=MM(b.GetDesignSettings().GetBoardThickness()),
                holes=holes(fps),
                parts={k: fps[k] for k in ("U7", "U2", "SW1", "SW3", "J1") if k in fps})
    # connectors on the port side (within 2 mm of the edge at the smallest y):
    # some 3D models are only .wrl, so the STEP misses them
    ymin = min(p[1] for p in data["outline"])
    data["port_parts"] = {k: v for k, v in fps.items() if k.startswith("J") and v["y0"] < ymin + 2.0}
    if len(sys.argv) > 3:
        h = pcbnew.LoadBoard(sys.argv[3])
        hf = footprints(h)
        hh = holes(hf)
        # the HDMI board sits on the module holes: same pattern, shifted
        dx = data["holes"][0][0] - hh[0][0]
        dy = data["holes"][0][1] - hh[0][1]
        for (a, b2), (c, d) in zip(sorted(data["holes"]), sorted(hh)):
            assert abs(a - c - dx) < 0.05 and abs(b2 - d - dy) < 0.05, "HDMI holes do not match the module holes"
        data["hdmi"] = dict(outline=[[x + dx, y + dy] for x, y in outline(h)], dx=dx, dy=dy,
                            thickness=MM(h.GetDesignSettings().GetBoardThickness()),
                            holes=[[x + dx, y + dy] for x, y in hh])
    json.dump(data, open(sys.argv[2], "w"), indent=1)
    print("%s: outline %d points, %d holes%s" % (sys.argv[2], len(data["outline"]), len(data["holes"]),
                                                  ", HDMI offset %.2f, %.2f" % (data["hdmi"]["dx"], data["hdmi"]["dy"]) if "hdmi" in data else ""))


main()

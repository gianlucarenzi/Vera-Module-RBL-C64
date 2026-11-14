#!/usr/bin/env python3
"""FPGA programming with iceprog, drawn in the style of the Fritzing
breadboard view (as ESP32-BOBOARD-5V/firmware/6502_monitor/docs/breadboard.py):
an FTDI FT232H breakout wired to J6 of the VERA module, with JP2, the BOOT0
and RESET buttons, the VERA READY LED and the four steps.

The J6 pinout, JP2, U9/U8 and the buttons come from the schematic (the VERA
sheets are the same on RBL-A2, RBL-XE and RBL-C64); the FT232H pins are the
iceprog defaults (ADBUS0 SCK, 1 MOSI, 2 MISO, 4 CS, 6 CDONE, 7 CRESET).

usage: fpga_prog_diagram.py OUTDIR BOARD_NAME
  writes OUTDIR/fpga_programming_en.svg and OUTDIR/fpga_programming_it.svg
"""
import os
import sys

W, H = 1240, 900

WIRE = {"SCK": "#ffe24d", "MOSI": "#418dd9", "MISO": "#47cc79", "SS": "#b673e6",
        "CDONE": "#ff7033", "CRESET": "#e8e8e8", "GND": "#404040"}

# J6 pin -> (signal, FT232H pin)
J6 = [(1, "5V/3V3", None), (2, "CDONE", "AD6"), (3, "CRESET", "AD7"), (4, "MISO", "AD2"),
      (5, "MOSI", "AD1"), (6, "SCK", "AD0"), (7, "SS", "AD4"), (8, "GND", "GND")]
FT = ["AD0", "AD1", "AD2", "AD3", "AD4", "AD5", "AD6", "AD7", "GND", "5V"]

TXT = {
    "en": dict(
        title="Programming the VERA FPGA flash with iceprog",
        sub="FTDI FT232H (or FT2232H channel A) on J6 of the VERA Module {b}  -  breadboard view",
        j6="J6  iceprog", jp2="JP2  FPGA PROGRAMMING", jp2c="cap ON while writing",
        boot="BOOT0", reset="RESET", ready="VERA READY", nc="not connected",
        usb="USB to the PC", steps=[
            ("1", "Stop the ESP32", "hold BOOT0, press and release RESET, release BOOT0 (download mode: its pins are inputs)"),
            ("2", "Close JP2", "CDONE to GND: U9 selects the flash U10, U8 takes the microSD off the SPI bus"),
            ("3", "Run iceprog", "iceprog -t   (ID: ef 40 15)|iceprog vera_module.bin|iceprog -c vera_module.bin"),
            ("4", "Open JP2, press RESET", "the ESP32 pulses CRESET, the FPGA loads the bitstream, VERA READY lights up"),
        ],
        legend="wires", note="J6.1 is 5 V (JP1) or 3.3 V (JP3) of the board: leave it unconnected. "
                             "With JP2 closed iceprog reports 'cdone: low': that is expected."),
    "it": dict(
        title="Programmare la flash dell'FPGA VERA con iceprog",
        sub="FTDI FT232H (o canale A di un FT2232H) su J6 del VERA Module {b}  -  vista breadboard",
        j6="J6  iceprog", jp2="JP2  FPGA PROGRAMMING", jp2c="cappuccio MESSO durante la scrittura",
        boot="BOOT0", reset="RESET", ready="VERA READY", nc="non collegato",
        usb="USB verso il PC", steps=[
            ("1", "Fermare l'ESP32", "tenere BOOT0, premere e rilasciare RESET, rilasciare BOOT0 (download mode: pin in ingresso)"),
            ("2", "Chiudere JP2", "CDONE a GND: U9 seleziona la flash U10, U8 stacca la microSD dal bus SPI"),
            ("3", "Lanciare iceprog", "iceprog -t   (ID: ef 40 15)|iceprog vera_module.bin|iceprog -c vera_module.bin"),
            ("4", "Aprire JP2, premere RESET", "l'ESP32 dà l'impulso su CRESET, l'FPGA carica il bitstream, si accende VERA READY"),
        ],
        legend="fili", note="J6.1 è il 5 V (JP1) o il 3,3 V (JP3) della scheda: lasciarlo scollegato. "
                            "Con JP2 chiuso iceprog segnala 'cdone: low': è normale."),
}


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def darker(c, f=0.6):
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (int(r * f), int(g * f), int(b * f))


def badge(o, x, y, n, r=15):
    o.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#e23b3b" stroke="#8a1414" stroke-width="2"/>')
    o.append(f'<text x="{x}" y="{y+6}" font-size="17" font-weight="bold" fill="#fff" text-anchor="middle">{n}</text>')


def button(o, x, y, label):
    o.append(f'<rect x="{x-20}" y="{y-20}" width="40" height="40" rx="4" fill="#c8c8c8" stroke="#6e6e6e" stroke-width="2"/>')
    o.append(f'<circle cx="{x}" cy="{y}" r="11" fill="#3a3a3a" stroke="#111"/>')
    for dx in (-20, 20):
        for dy in (-12, 12):
            o.append(f'<rect x="{x+dx-(4 if dx<0 else 0)}" y="{y+dy-2}" width="4" height="4" fill="#d4b04c"/>')
    o.append(f'<text x="{x}" y="{y+40}" font-size="13" font-weight="bold" fill="#fff" text-anchor="middle">{label}</text>')


def draw(board, lang, path):
    t = TXT[lang]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="DejaVu Sans, Arial, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         f'<text x="{W/2}" y="38" font-size="24" font-weight="bold" text-anchor="middle">{esc(t["title"])}</text>',
         f'<text x="{W/2}" y="62" font-size="14" fill="#555" text-anchor="middle">{esc(t["sub"].format(b=board))}</text>']

    # ---- FT232H breakout --------------------------------------------------
    PY0, PP = 150, 36
    fx, fy, fw, fh = 70, 110, 250, PY0 - 110 + PP * len(FT) + 10
    o.append(f'<rect x="{fx+4}" y="{fy+5}" width="{fw}" height="{fh}" rx="10" fill="#000" opacity="0.18"/>')
    o.append(f'<rect x="{fx}" y="{fy}" width="{fw}" height="{fh}" rx="10" fill="#1f3c88" stroke="#11235a" stroke-width="2"/>')
    # USB-C receptacle
    o.append(f'<rect x="{fx-22}" y="{fy+fh/2-26}" width="40" height="52" rx="8" fill="#c0c4c8" stroke="#7d8186" stroke-width="2"/>')
    o.append(f'<rect x="{fx-14}" y="{fy+fh/2-14}" width="24" height="28" rx="5" fill="#2b2b2b"/>')
    o.append(f'<text x="{fx}" y="{fy+fh+22}" font-size="12" fill="#333">&#8592; {esc(t["usb"])}</text>')
    # chip
    o.append(f'<rect x="{fx+50}" y="{fy+fh/2-50}" width="100" height="100" rx="4" fill="#202020"/>')
    o.append(f'<text x="{fx+100}" y="{fy+fh/2-4}" font-size="15" font-weight="bold" fill="#ddd" text-anchor="middle">FT232H</text>')
    o.append(f'<text x="{fx+100}" y="{fy+fh/2+16}" font-size="11" fill="#aaa" text-anchor="middle">MPSSE</text>')
    o.append(f'<text x="{fx+20}" y="{fy+28}" font-size="15" font-weight="bold" fill="#fff">FTDI FT232H</text>')
    o.append(f'<text x="{fx+20}" y="{fy+46}" font-size="11" fill="#c8d4ff">breakout</text>')
    # header column
    hx = fx + fw - 26
    o.append(f'<rect x="{hx-14}" y="{PY0-18}" width="28" height="{PP*len(FT)}" rx="2" fill="#2b2b2b"/>')
    fpos = {}
    for i, p in enumerate(FT):
        y = PY0 + i * PP
        fpos[p] = (hx, y)
        o.append(f'<rect x="{hx-5}" y="{y-5}" width="10" height="10" fill="#d4b04c" stroke="#8a6d1f"/>')
        used = any(f == p for _, _, f in J6)
        o.append(f'<text x="{hx-22}" y="{y+5}" font-size="13" text-anchor="end" '
                 f'fill="{"#ffffff" if used else "#8fa0d0"}">{p}</text>')

    # ---- VERA board --------------------------------------------------------
    bx, by, bw, bh = 640, 90, 560, 520
    o.append(f'<rect x="{bx+5}" y="{by+6}" width="{bw}" height="{bh}" rx="12" fill="#000" opacity="0.18"/>')
    o.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="12" fill="#1d6b3c" stroke="#0f4626" stroke-width="2"/>')
    o.append(f'<text x="{bx+bw-20}" y="{by+34}" font-size="17" font-weight="bold" fill="#fff" text-anchor="end">VERA Module {esc(board)}</text>')
    o.append(f'<text x="{bx+bw-20}" y="{by+52}" font-size="11" fill="#d8f0d8" text-anchor="end">(detail: FPGA, flash, J6, JP2, buttons)</text>')
    # chips
    def chip(x, y, w, h, l1, l2):
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="#202020"/>')
        o.append(f'<text x="{x+w/2}" y="{y+h/2-2}" font-size="13" font-weight="bold" fill="#ddd" text-anchor="middle">{l1}</text>')
        o.append(f'<text x="{x+w/2}" y="{y+h/2+15}" font-size="10" fill="#aaa" text-anchor="middle">{l2}</text>')
    chip(bx + 230, by + 230, 120, 120, "U2", "iCE40UP5K")
    chip(bx + 230, by + 90, 110, 60, "U10", "W25Q16 flash")
    chip(bx + 400, by + 120, 130, 130, "U7", "ESP32-S3")
    chip(bx + 400, by + 270, 70, 46, "U9", "CD4011")
    chip(bx + 400, by + 330, 100, 46, "U8", "74CBTLV3126")
    # J6 1x8 header, same pitch as the FT232H header
    jx = bx + 70
    JY0 = PY0 + PP / 2              # half a pitch off: no horizontal run overlaps another
    o.append(f'<rect x="{jx-14}" y="{JY0-18}" width="28" height="{PP*8}" rx="2" fill="#2b2b2b"/>')
    o.append(f'<text x="{jx}" y="{JY0-28}" font-size="14" font-weight="bold" fill="#fff" text-anchor="middle">{esc(t["j6"])}</text>')
    jpos = {}
    for k, (pin, sig, ft) in enumerate(J6):
        y = JY0 + k * PP
        jpos[pin] = (jx, y)
        o.append(f'<rect x="{jx-5}" y="{y-5}" width="10" height="10" fill="#d4b04c" stroke="#8a6d1f"/>')
        o.append(f'<text x="{jx+22}" y="{y+5}" font-size="13" fill="{"#ffffff" if ft else "#9fc7a9"}">'
                 f'{pin} {esc(sig)}</text>')
    # J6.1 not connected marker
    y1 = jpos[1][1]
    o.append(f'<path d="M{jx-30},{y1-8} l16,16 M{jx-30},{y1+8} l16,-16" stroke="#e23b3b" stroke-width="3"/>')
    o.append(f'<text x="{jx+22}" y="{y1+22}" font-size="11" fill="#ffb0b0">{esc(t["nc"])}</text>')
    # JP2 with jumper cap
    px, py = bx + 130, by + bh - 80
    o.append(f'<rect x="{px-20}" y="{py-14}" width="64" height="28" rx="2" fill="#2b2b2b"/>')
    for k in range(2):
        o.append(f'<rect x="{px-5+k*28}" y="{py-5}" width="10" height="10" fill="#d4b04c" stroke="#8a6d1f"/>')
    o.append(f'<rect x="{px-14}" y="{py-20}" width="52" height="40" rx="5" fill="#d42a2a" stroke="#7a1010" stroke-width="2" opacity="0.92"/>')
    o.append(f'<text x="{px+12}" y="{py+40}" font-size="13" font-weight="bold" fill="#fff" text-anchor="middle">{esc(t["jp2"])}</text>')
    o.append(f'<text x="{px+12}" y="{py+56}" font-size="11" fill="#ffd0d0" text-anchor="middle">{esc(t["jp2c"])}</text>')
    badge(o, px - 40, py, "2")
    badge(o, px + 70, py - 24, "4", 12)
    # buttons
    sx = bx + 330
    button(o, sx, py, t["boot"])
    button(o, sx + 110, py, t["reset"])
    badge(o, sx - 36, py - 30, "1")
    badge(o, sx + 146, py - 30, "4", 12)
    # LED
    lx, ly = bx + bw - 60, by + 470
    o.append(f'<circle cx="{lx}" cy="{ly}" r="22" fill="#7cff7c" opacity="0.35"/>')
    o.append(f'<rect x="{lx-9}" y="{ly-6}" width="18" height="12" rx="2" fill="#7cff7c" stroke="#2e8a2e"/>')
    o.append(f'<text x="{lx}" y="{ly+34}" font-size="12" font-weight="bold" fill="#fff" text-anchor="middle">{esc(t["ready"])}</text>')

    # ---- wires: FT pin -> vertical lane -> J6 pin --------------------------
    links = [(pin, sig, ft) for pin, sig, ft in J6 if ft]
    links.sort(key=lambda l: fpos[l[2]][1])
    segs = []
    for k, (pin, sig, ft) in enumerate(links):
        x1, y1 = fpos[ft]
        x2, y2 = jpos[pin]
        lane = 380 + k * 30
        pts = [(x1, y1), (lane, y1), (lane, y2), (x2, y2)]
        segs.append((pts, WIRE[sig]))
    for pts, c in segs:
        d = " ".join(f"{x},{y}" for x, y in pts)
        o.append(f'<polyline points="{d}" fill="none" stroke="{darker(c)}" stroke-width="8" stroke-linejoin="round" stroke-linecap="round"/>')
        o.append(f'<polyline points="{d}" fill="none" stroke="{c}" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>')
    for pts, c in segs:
        for x, y in (pts[0], pts[-1]):
            o.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{c}" stroke="{darker(c)}" stroke-width="1.5"/>')
    badge(o, 230, fy + fh + 40, "3")
    o.append(f'<text x="{252}" y="{fy+fh+46}" font-size="14" font-weight="bold" fill="#333">iceprog</text>')

    # ---- legend ---------------------------------------------------------------
    ly0 = by + bh + 50
    lxx = 70
    o.append(f'<text x="{lxx}" y="{ly0}" font-size="13" font-weight="bold" fill="#333">{esc(t["legend"])}:</text>')
    lxx += 60
    for sig in ("SCK", "MOSI", "MISO", "SS", "CDONE", "CRESET", "GND"):
        c = WIRE[sig]
        o.append(f'<line x1="{lxx}" y1="{ly0-5}" x2="{lxx+30}" y2="{ly0-5}" stroke="{darker(c)}" stroke-width="8" stroke-linecap="round"/>')
        o.append(f'<line x1="{lxx}" y1="{ly0-5}" x2="{lxx+30}" y2="{ly0-5}" stroke="{c}" stroke-width="5" stroke-linecap="round"/>')
        o.append(f'<text x="{lxx+40}" y="{ly0}" font-size="13">{sig}</text>')
        lxx += 140

    # ---- steps -----------------------------------------------------------------
    sy = ly0 + 30
    cw = (W - 140 - 3 * 16) / 4
    for i, (n, head, body) in enumerate(t["steps"]):
        x = 70 + i * (cw + 16)
        o.append(f'<rect x="{x}" y="{sy}" width="{cw}" height="150" rx="10" fill="#f4f6f8" stroke="#cfd6dd"/>')
        badge(o, x + 26, sy + 28, n)
        o.append(f'<text x="{x+50}" y="{sy+34}" font-size="14" font-weight="bold" fill="#222">{esc(head)}</text>')
        if "|" in body:                   # command lines, monospace
            for j, cmd in enumerate(body.split("|")):
                o.append(f'<text x="{x+16}" y="{sy+64+j*22}" font-size="12" font-family="DejaVu Sans Mono, monospace" fill="#1f3c88">{esc(cmd)}</text>')
            continue
        # wrap the body
        words, line, yy = body.split(), "", sy + 62
        for w_ in words:
            if len(line) + len(w_) + 1 > 36:
                o.append(f'<text x="{x+16}" y="{yy}" font-size="12" fill="#333">{esc(line)}</text>')
                line, yy = w_, yy + 18
            else:
                line = (line + " " + w_).strip()
        o.append(f'<text x="{x+16}" y="{yy}" font-size="12" fill="#333">{esc(line)}</text>')
    o.append(f'<text x="70" y="{H-20}" font-size="12" fill="#555">{esc(t["note"])}</text>')
    o.append('</svg>')
    open(path, "w").write("\n".join(o))


if __name__ == "__main__":
    out, board = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for lang in ("en", "it"):
        draw(board, lang, os.path.join(out, "fpga_programming_%s.svg" % lang))
    print("fpga_programming_en.svg, fpga_programming_it.svg in", out)

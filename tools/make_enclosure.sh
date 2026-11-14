#!/bin/bash
# Enclosure of the VERA module: two 3D-printable shells, made with FreeCAD
# from the KiCad 5 PCB and its STEP, with room for the VERA-HDMI-Expansion.
# See enclosure/README.md.
#
# Usage: tools/make_enclosure.sh CUT_Y [--no-anim]
#   CUT_Y   KiCad y (mm) where the case ends and the card edge fingers come
#           out: 151 for this board
#
# Needs: KiCad 5 (system, otherwise the KiCad 5 AppImage as "kicad5"),
# FreeCAD 0.19 or later (freecadcmd, freecad), xvfb-run and ffmpeg (or
# ImageMagick) for the animation. The STEP is images/VERA-MODULE-RBL.step (output_job.sh);
# the HDMI board is looked for in ../Vera-HDMI-Expansion and ~/Progetti/*/
# (or HDMI_DIR=...), optional.
set -e
cd "$(dirname "$0")/.."
CUT=${1:?usage: tools/make_enclosure.sh CUT_Y [--no-anim]}
PCB=VERA-MODULE-RBL
NAME=${ENC_NAME:-VERA-$(basename "$(pwd)" | sed 's/^Vera-Module-//')-enclosure}
OUT=enclosure
HDMI_DIR=${HDMI_DIR:-$(ls -d ../Vera-HDMI-Expansion "$HOME"/Progetti/*/Vera-HDMI-Expansion 2>/dev/null | head -1)}

command -v freecadcmd >/dev/null || { echo "freecadcmd not found: install FreeCAD (apt install freecad)"; exit 1; }
[ -f images/${PCB}.step ] || { echo "images/${PCB}.step missing: run ./output_job.sh first"; exit 1; }
mkdir -p ${OUT}

HDMI_PCB= ; HDMI_STEP=
if [ -f "${HDMI_DIR}/VERA-HDMI-Expansion.kicad_pcb" ] && [ -f "${HDMI_DIR}/images/VERA-HDMI-Expansion.step" ]; then
	HDMI_PCB=${HDMI_DIR}/VERA-HDMI-Expansion.kicad_pcb
	HDMI_STEP=${HDMI_DIR}/images/VERA-HDMI-Expansion.step
else
	echo "VERA-HDMI-Expansion not found in ${HDMI_DIR}: enclosure without it (HDMI_DIR=... to set it)"
fi

echo "[1/4] Board data from the PCB (pcbnew of KiCad 5)"
./run_pcbnew.sh tools/enclosure_data.py ${PCB}.kicad_pcb ${OUT}/board.json ${HDMI_PCB}

echo "[2/4] Shells (FreeCAD, a few minutes: most of it reads the STEP)"
ENC_DATA=${OUT}/board.json ENC_STEP=images/${PCB}.step ENC_HDMI=${HDMI_STEP} ENC_CUT=${CUT} \
	ENC_NAME=${NAME} ENC_OUT=${OUT} freecadcmd tools/make_enclosure.py 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | \
	grep -vE "^\s*$|\*\*\*|Step File|Transfer|WorkSession|Statistics"

[ "$2" = "--no-anim" ] && exit 0
if ! command -v xvfb-run >/dev/null || { ! command -v ffmpeg >/dev/null && ! command -v convert >/dev/null; }; then
	echo "xvfb-run, or ffmpeg / ImageMagick, missing: no animation (apt install xvfb ffmpeg)"
	exit 0
fi
echo "[3/4] Assembly frames (FreeCAD GUI on a virtual display, about 15 minutes)"
FRAMES=$(mktemp -d)
trap 'rm -rf "${FRAMES}"' EXIT
ENC_DOC=${OUT}/${NAME}.FCStd ENC_FRAMES=${FRAMES} \
	xvfb-run -a -s "-screen 0 1280x1024x24" freecad tools/enclosure_assembly.py >/dev/null 2>&1 || true
[ -n "$(ls ${FRAMES})" ] || { echo "no frames rendered"; exit 1; }
echo "[4/4] GIF"
GIF=${OUT}/${NAME}-assembly.gif
if command -v ffmpeg >/dev/null; then
	# one palette for the whole animation: much faster than ImageMagick
	ffmpeg -v error -y -framerate 16 -i ${FRAMES}/f%04d.png \
		-vf "scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer" \
		-loop 0 ${GIF}
else
	convert -delay 6 -loop 0 -resize 720x540 ${FRAMES}/*.png ${GIF}
fi
echo "done: ${OUT}/${NAME}-{bottom,top}.{step,stl}, ${NAME}.FCStd, ${NAME}-assembly.gif"

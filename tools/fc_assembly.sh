#!/bin/bash
# FreeCAD documents to check the clearances of the module in the C64
# (not used by the renders):
#   enclosure/VERA-RBL-C64-module.FCStd  the module as one App::Part (board,
#       HDMI, the four standoffs, bottom, top and back panel of the
#       -backpanel enclosure), origin at the tip of the card edge fingers
#   enclosure/VERA-RBL-C64-in-C64.FCStd  the C64 of the desk scene (case and
#       keyboard), its motherboard (images/C64-Motherboard-Replice.wrl) on the
#       bosses of the case, and the module with its fingers in the expansion
#       port socket of that motherboard
# The enclosure is enclosure/VERA-RBL-C64-enclosure-backpanel.FCStd as it is
# (tools/make_enclosure.sh or the Enclosure workflow first, when it changes).
#
# Usage: tools/fc_assembly.sh
# Needs: Blender 4.2 (BLENDER=..., default blender-4.2), FreeCAD 0.19 or later,
# xvfb-run, python3 with numpy and Pillow, the LFS files (git lfs pull).
set -e -o pipefail
cd "$(dirname "$0")/.."
BLENDER=${BLENDER:-blender-4.2}
NAME=VERA-RBL-C64
COMPUTER=C64
MB_WRL=images/C64-Motherboard-Replice.wrl
# the motherboard on the bosses of the case: its seven 4 mm holes on the
# bosses' axes (within 1 mm), its bottom face on their tops (z 9)
MB_PLACE='[213.2, -46.4, 9.8]'
# the module in that motherboard's expansion port (a right angle socket, the
# slot facing the rear): fingers centred on the socket, the board's mid plane
# on the slot's (5.5 mm above the motherboard's bottom face), the tip 0.5 mm
# from the bottom of the slot. The teaser's pose differs (tools/desk_scene.py).
MODULE_T='[87.55, -142.6, 14.5]'

for f in ${MB_WRL} enclosure/${NAME}-enclosure-backpanel.FCStd; do
	[ -s "$f" ] || { echo "$f missing"; exit 1; }
	head -c 200 "$f" | grep -q "^version https://git-lfs" && { echo "$f is a Git LFS pointer: git lfs pull"; exit 1; }
done
TMP=$(mktemp -d)
trap 'rm -rf "${TMP}"' EXIT

echo "[1/3] The C64 of the desk scene (Blender, no rendering)"
python3 tools/make_screens.py "${TMP}/screens" >/dev/null
CTX_OUT=${TMP}/ctx RENDER_MODE=desk DESK_MACHINE=c64 DESK_SCREENS=${TMP}/screens \
	RENDER_FRAMES_DIR=${TMP}/frames RENDER_FRAMES=100-100 "${BLENDER}" -b -P tools/fc_context.py 2>&1 | grep -E "^CTX|Error" || true
[ -s "${TMP}/ctx/placement.json" ] || { echo "Blender did not write the C64 meshes"; exit 1; }

echo "[2/3] The motherboard (VRML to STL)"
python3 tools/wrl2stl.py ${MB_WRL} "${TMP}/mb"

echo "[3/3] FreeCAD documents"
rm -f enclosure/${NAME}-module.FCStd enclosure/${NAME}-in-${COMPUTER}.FCStd
REPO=$(pwd) NAME=${NAME} COMPUTER=${COMPUTER} CTX=${TMP}/ctx MB=${TMP}/mb MB_PLACE=${MB_PLACE} MODULE_T=${MODULE_T} \
	xvfb-run -a -s "-screen 0 1280x1024x24" freecad tools/fc_assembly.py 2>&1 | grep -E "^FCASM|Error" || true
rm -f enclosure/*.FCStd1
for f in ${NAME}-module.FCStd ${NAME}-in-${COMPUTER}.FCStd; do
	[ -s enclosure/$f ] || { echo "FreeCAD did not write enclosure/$f"; exit 1; }
done
echo "done: enclosure/${NAME}-module.FCStd, enclosure/${NAME}-in-${COMPUTER}.FCStd"

#!/bin/bash
# VRML of a KiCad 5 board with kicad-cli (KiCad 7+): the 3D models of the
# parts plus the board layers (solder mask, silkscreen, copper), the best
# looking VRML for renders. The KiCad 5 3D models the board uses
# (${KISYS3DMOD}/...) are taken one by one from the KiCad 5 AppImage, so the
# whole library (about 5 GB) is never extracted; ${KILIBPATH} is the
# RetroBitLab-Library.
#
# Usage: tools/make_vrml.sh BOARD.kicad_pcb OUT.wrl
# Environment:
#   KICAD5_APPIMAGE  the KiCad 5 AppImage (v2.2.0+)
#   KILIBPATH        the RetroBitLab-Library
#   MODELS_DIR       where the models are extracted (default /tmp/kicad5-models)
set -e -o pipefail
PCB=${1:?usage: $0 BOARD.kicad_pcb OUT.wrl}
OUT=${2:?usage: $0 BOARD.kicad_pcb OUT.wrl}
: "${KICAD5_APPIMAGE:?KICAD5_APPIMAGE: the KiCad 5 AppImage}"
: "${KILIBPATH:?KILIBPATH: the RetroBitLab-Library}"
MODELS_DIR=${MODELS_DIR:-/tmp/kicad5-models}
APPIMAGE=$(readlink -f "${KICAD5_APPIMAGE}")
PKG=usr/share/kicad/modules/packages3d          # KISYS3DMOD in the AppImage

mkdir -p "${MODELS_DIR}"
n=0
for rel in $(grep -o '(model ${KISYS3DMOD}/[^ )]*' "${PCB}" | sed 's/^(model ${KISYS3DMOD}\///' | sort -u); do
	[ -f "${MODELS_DIR}/${PKG}/${rel}" ] && continue
	(cd "${MODELS_DIR}" && "${APPIMAGE}" --appimage-extract "${PKG}/${rel}" >/dev/null)
	[ -f "${MODELS_DIR}/squashfs-root/${PKG}/${rel}" ] || { echo "warning: ${rel} not in the AppImage"; continue; }
	mkdir -p "$(dirname "${MODELS_DIR}/${PKG}/${rel}")"
	mv "${MODELS_DIR}/squashfs-root/${PKG}/${rel}" "${MODELS_DIR}/${PKG}/${rel}"
	n=$((n + 1))
done
rm -rf "${MODELS_DIR}/squashfs-root"
echo "$(basename "${PCB}"): ${n} KiCad 5 models extracted"
for rel in $(grep -o '(model ${KILIBPATH}/[^ )]*' "${PCB}" | sed 's/^(model ${KILIBPATH}\///' | sort -u); do
	[ -f "${KILIBPATH}/${rel}" ] || echo "warning: ${KILIBPATH}/${rel} missing"
done

mkdir -p "$(dirname "${OUT}")"
rm -f "${OUT}"
KISYS3DMOD="${MODELS_DIR}/${PKG}" kicad-cli version
KISYS3DMOD="${MODELS_DIR}/${PKG}" kicad-cli pcb export vrml -o "${OUT}" --force --no-dnp "${PCB}"
[ -s "${OUT}" ] || { echo "no VRML written"; exit 1; }
ls -l "${OUT}"

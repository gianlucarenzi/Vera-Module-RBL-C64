#!/bin/bash
# Checks, before output_job.sh, that every part of the JLCPCB BOM can be
# assembled by JLCPCB: in their parts library and with enough stock for the
# boards to make. Stops with an error (exit 1) and lists candidates when a
# part is missing, out of stock or short: change it in the schematic first.
#
# The BOM is built from the schematic as output_job.sh does, into a
# temporary folder (no project file is written). Stock, prices and
# alternatives come live from the jlcpcb.com parts search.
#
# Usage: ./check_jlcpcb_stock.sh [-n BOARDS]
#   -n BOARDS   boards to assemble (default 5)

PCBNAME=VERA-MODULE-RBL
BOARDS=5
PYTHON3=$(which python3)

while [ $# -gt 0 ]; do
	case "$1" in
		-n) BOARDS=$2; shift 2 ;;
		*) echo "Usage: $0 [-n BOARDS]"; exit 2 ;;
	esac
done

cd "$(dirname "$0")" || exit 2

WORK=$(mktemp -d)
trap 'rm -rf "${WORK}"' EXIT
${PYTHON3} sch2bomxml.py ${PCBNAME}.sch "${WORK}/bom.xml" >/dev/null || exit 2
${PYTHON3} generate_bom.py "${WORK}/bom.xml" "${WORK}/bom.csv" >/dev/null || exit 2
${PYTHON3} jlcpcb-check-bom.py "${WORK}/bom.csv" "${WORK}/jlcpcb-bom.csv" >/dev/null
[ -s "${WORK}/jlcpcb-bom.csv" ] || { echo "Error on creating the JLCPCB BOM."; exit 2; }

${PYTHON3} jlcpcb-stock-check.py --boards "${BOARDS}" "${WORK}/jlcpcb-bom.csv"

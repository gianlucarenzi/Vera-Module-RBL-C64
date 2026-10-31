#!/bin/sh
# Route the board from scratch with fastroute: GND and POWER as pure planes,
# a via to its plane for every GND/3V3 SMD pad, the address and data buses
# first and then everything else. No length tuning (it overlapped traces).
#
# usage: tools/route.sh WORKDIR
#   needs VERA-MODULE-RBL.dsn exported from pcbnew 5 (File > Export >
#   Specctra DSN) with the zones in place; the result is WORKDIR/final.ses,
#   to import with File > Import > Specctra Session, then B and DRC.
#   Live view of each stage on http://127.0.0.1:7878
#
#   fastroute must be installed system wide from its Debian package, see
#   https://github.com/gianlucarenzi/fastroute (FASTROUTE=/path/to/fastroute
#   uses another binary instead).
set -e
TOOLS=$(cd "$(dirname "$0")" && pwd)
PROJ=$(dirname "$TOOLS")
WORK=${1:?usage: tools/route.sh WORKDIR}
FR=${FASTROUTE:-$(command -v fastroute || true)}
if [ -z "$FR" ] || [ ! -x "$FR" ]; then
	echo "fastroute is not installed: build and install its Debian package," >&2
	echo "see https://github.com/gianlucarenzi/fastroute" >&2
	echo "(git clone it, scripts/build-deb.sh, sudo apt install ./dist/fastroute_*.deb)" >&2
	exit 1
fi
echo "Using $FR ($("$FR" --version))"
COMMON="--router.min_trace_width_um=200 --router.plane_nets=GND,3V3 --live"

mkdir -p "$WORK"
cd "$WORK"
python3 "$TOOLS/prep_dsn.py" "$PROJ/VERA-MODULE-RBL.dsn" board.dsn --clear
python3 "$TOOLS/plane_vias.py" "$PROJ/VERA-MODULE-RBL.kicad_pcb" board.dsn board_pv.dsn GND,3V3

# stage 1: only AddressBus and DataBus, on an empty board
"$FR" -de board_pv.dsn -do bus.ses --report=bus.json --max-time=2400 \
    --router.autorouter.ignore_net_classes=kicad_default,90R,Power $COMMON > bus.log 2>&1

# stage 2: the rest; the plane vias stay fixed in the DSN, so they are
# stripped from the bus session (a session is not fixed, and loading them
# twice gives hundreds of via/via violations)
python3 "$TOOLS/strip_protect_ses.py" bus.ses bus_np.ses
"$FR" -de board_pv.dsn -do board.ses --initial-session=bus_np.ses --report=report.json \
    --max-time=7200 $COMMON > run.log 2>&1

python3 "$TOOLS/dedupe_ses.py" board.ses final.ses
python3 "$TOOLS/ses_narrow.py" final.ses
echo "unrouted connections: see $WORK/report.json"

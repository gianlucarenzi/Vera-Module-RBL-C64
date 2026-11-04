#!/bin/sh
# Route only the missing connections with fastroute, keeping all the existing
# tracks and vias unchanged (unlike tools/route.sh, which routes from scratch).
#
# usage: tools/route_incremental.sh WORKDIR [MAX_SECONDS]
#   needs VERA-MODULE-RBL.dsn exported from pcbnew 5 (File > Export >
#   Specctra DSN) from the saved board, with the zones filled, and KiCad
#   closed (the .kicad_pcb is read). The result is VERA-MODULE-RBL.ses in the
#   project, to import with File > Import > Specctra Session, then B and DRC.
#   Live view on http://127.0.0.1:7878
#
# What it does:
#   - GND and POWER become pure planes (no tracks); the GND pours of F.Cu and
#     B.Cu stay (outer pours are not obstacles for fastroute, and the pads
#     already joined by them need no via);
#   - every multi-point wire is split into segments (tools/split_dsn_wires.py):
#     KiCad 5 puts T junctions on intermediate vertices, which fastroute does
#     not see, so complete nets would look broken;
#   - no SMD fanout stage (it would add vias to the pins of the plane nets);
#   - the session is filtered (tools/filter_ses.py): existing wiring exactly
#     once and unchanged, new wiring only on the nets that were incomplete
#     (tools/unrouted_nets.py). KiCad 5 replaces ALL tracks on session import,
#     so filter_ses.py refuses a session that lacks existing wiring.
set -e
TOOLS=$(cd "$(dirname "$0")" && pwd)
PROJ=$(dirname "$TOOLS")
WORK=${1:?usage: tools/route_incremental.sh WORKDIR [MAX_SECONDS]}
MAXT=${2:-1800}
FR=${FASTROUTE:-$(command -v fastroute || true)}
if [ -z "$FR" ] || [ ! -x "$FR" ]; then
	echo "fastroute is not installed, see tools/route.sh" >&2
	exit 1
fi
if wmctrl -l 2>/dev/null | grep -q -i -E 'kicad|pcbnew'; then
	echo "close KiCad first (the board is read and the session is written)" >&2
	exit 1
fi
mkdir -p "$WORK"
WORK=$(cd "$WORK" && pwd)

NETS=$(python3 "$TOOLS/unrouted_nets.py" "$PROJ/VERA-MODULE-RBL.kicad_pcb" 2>"$WORK/unrouted.txt")
cat "$WORK/unrouted.txt"
[ -n "$NETS" ] || { echo "nothing to route"; exit 0; }

python3 - "$PROJ/VERA-MODULE-RBL.dsn" "$WORK/planes.dsn" <<'EOF'
import re, sys
t = open(sys.argv[1]).read()
for layer in ('GND', 'POWER'):
    t, n = re.subn(r'(\(layer %s\s*\(type )signal\)' % layer, r'\1power)', t)
    assert n == 1, layer
open(sys.argv[2], 'w').write(t)
EOF
python3 "$TOOLS/split_dsn_wires.py" "$WORK/planes.dsn" "$WORK/board.dsn"

cd "$WORK"
"$FR" -de board.dsn -do board.ses --report=report.json --diagnose --max-time="$MAXT" \
	--router.min_trace_width_um=200 --router.fanout.enabled=false --live > run.log 2>&1

python3 "$TOOLS/filter_ses.py" board.dsn board.ses final.ses "$NETS"
python3 "$TOOLS/ses_narrow.py" final.ses
cp final.ses "$PROJ/VERA-MODULE-RBL.ses"
echo "session: $PROJ/VERA-MODULE-RBL.ses; still unrouted (with diagnosis): $WORK/report.json"

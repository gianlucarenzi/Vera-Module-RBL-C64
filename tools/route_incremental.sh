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
#
# INNER_FALLBACK=1 tools/route_incremental.sh WORKDIR [MAX_SECONDS]
#   if connections are still unrouted after the first stage, a second stage
#   starts from its session with GND and POWER routable as signal layers at a
#   high trace cost (INNER_COST, default 25 times the outer layers), so the
#   planes are used only where F.Cu/B.Cu have no room. A trace on a plane cuts
#   it: after the import refill the zones and check in the DRC that no GND or
#   3V3 pad was left on an island. Explicit costs are needed: with 4 signal
#   layers and no costs fastroute makes the OUTER layers more expensive.
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

LEFT=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["stats"]["unrouted"])' report.json)
echo "stage 1: $LEFT connections unrouted"
DSN=board.dsn
SES=board.ses
REPORT=report.json
if [ "${INNER_FALLBACK:-0}" = 1 ] && [ "$LEFT" -gt 0 ]; then
	C=${INNER_COST:-25}
	# GND and POWER stay signal layers, as exported by KiCad
	python3 "$TOOLS/split_dsn_wires.py" "$PROJ/VERA-MODULE-RBL.dsn" board_inner.dsn
	# the fixed wiring comes from the DSN: drop it from the starting session
	python3 "$TOOLS/strip_protect_ses.py" board.ses stage1_np.ses
	"$FR" -de board_inner.dsn -do board_inner.ses --initial-session=stage1_np.ses \
		--report=report_inner.json --diagnose --max-time="$MAXT" \
		--router.min_trace_width_um=200 --router.fanout.enabled=false \
		--router.layers.preferred_direction_trace_cost=1,$C,$C,1 \
		--router.layers.undesired_direction_trace_cost=1,$C,$C,1 --live > run_inner.log 2>&1
	LEFT2=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["stats"]["unrouted"])' report_inner.json)
	echo "stage 2 (GND/POWER at cost $C): $LEFT2 connections unrouted"
	if [ "$LEFT2" -lt "$LEFT" ]; then
		DSN=board_inner.dsn
		SES=board_inner.ses
		REPORT=report_inner.json
	else
		echo "stage 2 did not help: keeping the stage 1 session"
	fi
fi

python3 "$TOOLS/filter_ses.py" "$DSN" "$SES" final.ses "$NETS"
python3 - final.ses <<'EOF'
import re, sys, collections
c = collections.Counter(m.group(1) for m in re.finditer(r'\(wire\s*\(path (\S+) [^)]*\)(?!\s*\(type protect\))', open(sys.argv[1]).read()))
inner = {k: v for k, v in c.items() if k in ('GND', 'POWER')}
if inner:
    print('NEW TRACES ON THE PLANES:', inner, '- refill and check GND/3V3 islands in the DRC')
EOF
python3 "$TOOLS/ses_narrow.py" final.ses
cp final.ses "$PROJ/VERA-MODULE-RBL.ses"
echo "session: $PROJ/VERA-MODULE-RBL.ses; still unrouted (with diagnosis): $WORK/$REPORT"

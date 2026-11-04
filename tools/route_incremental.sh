#!/bin/sh
# Route only the missing connections with fastroute, keeping all the existing
# tracks and vias unchanged (tools/route.sh, where present, routes from
# scratch instead).
#
# usage: tools/route_incremental.sh WORKDIR [MAX_SECONDS]
#   works on the only .kicad_pcb of the project (BOARD below); needs
#   BOARD.dsn exported from pcbnew 5 (File > Export > Specctra DSN) from the
#   saved board, with the zones filled, and KiCad closed (the .kicad_pcb is
#   read). The result is BOARD.ses in the project, to import with File >
#   Import > Specctra Session, then B and DRC. Live view on
#   http://127.0.0.1:7878
#
# What it does:
#   - the inner copper layers (read from the .kicad_pcb) become pure planes
#     (no new tracks); the pours of F.Cu and B.Cu stay (outer pours are not
#     obstacles for fastroute, and the pads already joined by them need no
#     via); existing tracks on the inner layers stay as they are;
#   - every multi-point wire is split into segments (tools/split_dsn_wires.py):
#     KiCad 5 puts junctions on intermediate vertices and in the middle of
#     segments, which fastroute does not see, so complete nets would look
#     broken;
#   - no SMD fanout stage (it would add vias to the pins of the plane nets);
#   - the session is filtered (tools/filter_ses.py): existing wiring exactly
#     once and unchanged, new wiring only on the nets that were incomplete
#     (tools/unrouted_nets.py). KiCad 5 replaces ALL tracks on session import,
#     so filter_ses.py refuses a session that lacks existing wiring.
#
# INNER_FALLBACK=1 tools/route_incremental.sh WORKDIR [MAX_SECONDS]
#   if connections are still unrouted after the first stage, a second stage
#   starts from its session with the inner layers routable as signal layers
#   at a high trace cost (INNER_COST, default 25 times the outer layers), so
#   they are used only where F.Cu/B.Cu have no room. A trace on a plane cuts
#   it: after the import refill the zones and check in the DRC that no pad of
#   the plane nets was left on an island. Explicit costs are needed: with 4
#   signal layers and no costs fastroute makes the OUTER layers more
#   expensive.
set -e
TOOLS=$(cd "$(dirname "$0")" && pwd)
PROJ=$(dirname "$TOOLS")
WORK=${1:?usage: tools/route_incremental.sh WORKDIR [MAX_SECONDS]}
MAXT=${2:-1800}
C=${INNER_COST:-25}
FR=${FASTROUTE:-$(command -v fastroute || true)}
if [ -z "$FR" ] || [ ! -x "$FR" ]; then
	echo "fastroute is not installed: build and install its Debian package," >&2
	echo "see https://github.com/gianlucarenzi/fastroute" >&2
	exit 1
fi
if wmctrl -l 2>/dev/null | grep -q -i -E 'kicad|pcbnew'; then
	echo "close KiCad first (the board is read and the session is written)" >&2
	exit 1
fi
eval "$(python3 "$TOOLS/board_info.py" "$PROJ" "$C")"
PCB="$PROJ/$BOARD.kicad_pcb"
if [ "$PCB" -nt "$PROJ/$BOARD.dsn" ]; then
	echo "$BOARD.dsn is missing or older than the board: export it again" >&2
	exit 1
fi
mkdir -p "$WORK"
WORK=$(cd "$WORK" && pwd)

NETS=$(python3 "$TOOLS/unrouted_nets.py" "$PCB" 2>"$WORK/unrouted.txt")
cat "$WORK/unrouted.txt"
[ -n "$NETS" ] || { echo "nothing to route"; exit 0; }

python3 - "$PROJ/$BOARD.dsn" "$WORK/planes.dsn" "$INNER" <<'EOF'
import re, sys
t = open(sys.argv[1]).read()
for layer in filter(None, sys.argv[3].split(',')):
    t, n = re.subn(r'(\(layer %s\s*\(type )signal\)' % re.escape(layer), r'\1power)', t)
    # a layer that KiCad already calls "power" is exported as such
    assert n == 1 or re.search(r'\(layer %s\s*\(type power\)' % re.escape(layer), t), layer
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
	# the inner layers stay signal layers, as exported by KiCad
	python3 "$TOOLS/split_dsn_wires.py" "$PROJ/$BOARD.dsn" board_inner.dsn
	# the fixed wiring comes from the DSN: drop it from the starting session
	python3 "$TOOLS/strip_protect_ses.py" board.ses stage1_np.ses
	"$FR" -de board_inner.dsn -do board_inner.ses --initial-session=stage1_np.ses \
		--report=report_inner.json --diagnose --max-time="$MAXT" \
		--router.min_trace_width_um=200 --router.fanout.enabled=false \
		--router.layers.preferred_direction_trace_cost="$COSTS" \
		--router.layers.undesired_direction_trace_cost="$COSTS" --live > run_inner.log 2>&1
	LEFT2=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["stats"]["unrouted"])' report_inner.json)
	echo "stage 2 ($INNER at cost $C): $LEFT2 connections unrouted"
	if [ "$LEFT2" -lt "$LEFT" ]; then
		DSN=board_inner.dsn
		SES=board_inner.ses
		REPORT=report_inner.json
	else
		echo "stage 2 did not help: keeping the stage 1 session"
	fi
fi

python3 "$TOOLS/filter_ses.py" "$DSN" "$SES" final.ses "$NETS"
python3 - final.ses "$INNER" <<'EOF'
import re, sys, collections
inner = set(filter(None, sys.argv[2].split(',')))
c = collections.Counter(m.group(1) for m in re.finditer(r'\(wire\s*\(path (\S+) [^)]*\)(?!\s*\(type protect\))', open(sys.argv[1]).read()))
on = {k: v for k, v in c.items() if k in inner}
if on:
    print('NEW TRACES ON THE INNER LAYERS:', on, '- refill and check the plane nets for islands in the DRC')
EOF
python3 "$TOOLS/ses_narrow.py" final.ses
cp final.ses "$PROJ/$BOARD.ses"
echo "session: $PROJ/$BOARD.ses; still unrouted (with diagnosis): $WORK/$REPORT"

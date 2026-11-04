#!/bin/sh
# Let fastroute's optimizer shorten the tracks and drop vias, but only on the
# wiring added after a given git commit; everything else stays fixed.
#
# usage: tools/optimize_new.sh BASE_COMMIT WORKDIR [MAX_SECONDS]
#   BASE_COMMIT  the commit whose wiring is kept unchanged (e.g. the last one
#                with the validated routing); tracks and vias added since then
#                in the project's only .kicad_pcb (BOARD) are optimized
#   needs BOARD.dsn exported from pcbnew 5 (File > Export > Specctra DSN) from
#   the saved board, and KiCad closed. The result is BOARD.ses in the
#   project. Live view on http://127.0.0.1:7878
#
# Import in pcbnew: remove the teardrops first (they would stay on the old
# track positions), File > Import > Specctra Session, add the teardrops
# again, refill (B), DRC.
#
# The inner layers stay signal layers at INNER_COST (default 25) times the
# outer layers, so new tracks already on them can move but the optimizer
# prefers F.Cu/B.Cu. The optimizer stops when a pass improves by less than
# 0.5 % (the threshold is a fraction: 0.005).
#
# fastroute's clearance report is stricter than KiCad's DRC: it checks
# copper of the same net too, and it sees vias and trace ends as octagons.
# Use it only to compare runs; KiCad's DRC is the reference.
set -e
TOOLS=$(cd "$(dirname "$0")" && pwd)
PROJ=$(dirname "$TOOLS")
BASE=${1:?usage: tools/optimize_new.sh BASE_COMMIT WORKDIR [MAX_SECONDS]}
WORK=${2:?usage: tools/optimize_new.sh BASE_COMMIT WORKDIR [MAX_SECONDS]}
MAXT=${3:-1800}
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

git -C "$PROJ" show "$BASE:$BOARD.kicad_pcb" > "$WORK/base.kicad_pcb"
python3 "$TOOLS/new_items.py" "$WORK/base.kicad_pcb" "$PCB" "$WORK/new_items.json"
NETS=$(python3 -c 'import json, sys; print(",".join(sorted({o["net"] for o in json.load(open(sys.argv[1]))})))' "$WORK/new_items.json")
[ -n "$NETS" ] || { echo "no new wiring since $BASE"; exit 0; }

python3 "$TOOLS/split_dsn_wires.py" "$PROJ/$BOARD.dsn" "$WORK/split.dsn"
python3 "$TOOLS/unprotect_new.py" "$WORK/split.dsn" "$WORK/new_items.json" "$WORK/opt.dsn"

cd "$WORK"
"$FR" -de opt.dsn -do opt.ses --report=report.json --diagnose --max-time="$MAXT" \
	--router.fanout.enabled=false --router.min_trace_width_um=200 \
	--router.layers.preferred_direction_trace_cost="$COSTS" \
	--router.layers.undesired_direction_trace_cost="$COSTS" \
	--router.optimizer.improvement_threshold=0.005 --live > run.log 2>&1
grep -E "Optimizer pass #[0-9]+: optimizer score|Stopping optimizer" run.log || true

python3 "$TOOLS/filter_ses.py" opt.dsn opt.ses final.ses "$NETS"
python3 "$TOOLS/ses_narrow.py" final.ses
python3 - new_items.json final.ses <<'EOF'
import json, math, re, sys, collections
old = json.load(open(sys.argv[1]))
L0 = sum(math.hypot(o['a'][0] - o['b'][0], o['a'][1] - o['b'][1]) / 1e6 for o in old if o['kind'] == 'track')
V0 = sum(1 for o in old if o['kind'] == 'via')
t = open(sys.argv[2]).read()
L1 = 0.0
V1 = 0
for m in re.finditer(r'\(net ("[^"]*"|[^\s()]+)\s*\n(.*?)\n      \)', t, re.S):
    for w in re.finditer(r'\(path (\S+) (\d+)\s+([-\d\s]+)\)(?!\s*\(type protect\))', m.group(2)):
        p = list(map(int, w.group(3).split()))
        L1 += sum(math.hypot(p[i + 2] - p[i], p[i + 3] - p[i + 1]) for i in range(0, len(p) - 2, 2)) / 1e4
    V1 += len(re.findall(r'\(via "[^"]*" -?\d+ -?\d+\s*\)', m.group(2)))
print('new wiring: %.1f mm -> %.1f mm, %d -> %d vias' % (L0, L1, V0, V1))
EOF
cp final.ses "$PROJ/$BOARD.ses"
echo "session: $PROJ/$BOARD.ses (remove the teardrops before the import)"

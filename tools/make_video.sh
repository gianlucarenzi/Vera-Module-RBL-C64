#!/bin/bash
# The assembly frames of tools/render_enclosure.py (RENDER_MODE=anim) as:
#   OUT-assembly.gif   the animation, 720 px wide
#   OUT-assembly.mp4   the animation, H.264
#   OUT-teaser.mp4     the animation fading to black in its last second, the
#                      end credits (CREDITS, tools/make_credits.py)
#                      scrolling up, one screen every CREDITS_SCREEN s, then
#                      the end card (TITLE, big and bold, in the centre,
#                      SUBTITLE at the bottom) fading in, held, and fading
#                      out in its last CARD_FADE of CARD seconds. With MUSIC
#                      (from MUSIC_START s, loudness normalised to -16 LUFS),
#                      the track fades in over 1.5 s, plays under the
#                      credits and fades out with the end card
#
# Usage: tools/make_video.sh FRAMES_DIR OUT [MUSIC]
# Environment: FPS (24), TITLE ("COMING SOON"), SUBTITLE ("Available Q1 2027"),
#              CARD (5 s), CARD_FADE (3 s), FONT (DejaVu Sans Bold),
#              MUSIC_START (0 s), MUSIC_CREDIT (credit lines, | separated),
#              CREDITS (tools/credits.txt), CREDITS_SCREEN (5 s),
#              CREDITS_HOLD (3 s, stop on the logos)
set -e -o pipefail
FRAMES=${1:?usage: $0 FRAMES_DIR OUT [MUSIC]}
OUT=${2:?usage: $0 FRAMES_DIR OUT [MUSIC]}
MUSIC=$3
FPS=${FPS:-24}
TITLE=${TITLE:-COMING SOON}
SUBTITLE=${SUBTITLE:-Available Q1 2027}
CARD=${CARD:-5}
MUSIC_START=${MUSIC_START:-0}
CARD_FADE=${CARD_FADE:-3}
FONT=${FONT:-/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf}
[ -f "${FONT}" ] || { echo "font ${FONT} missing (apt install fonts-dejavu-core)"; exit 1; }

N=$(ls "${FRAMES}"/f*.png | wc -l)
[ "${N}" -gt 0 ] || { echo "no frames in ${FRAMES}"; exit 1; }
SIZE=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "${FRAMES}/f0001.png")
D=$(awk "BEGIN{printf \"%.3f\", ${N}/${FPS}}")              # animation length (s)
FADE_AT=$(awk "BEGIN{printf \"%.3f\", ${D}-1}")
echo "${N} frames, ${SIZE}, ${D} s at ${FPS} fps"
mkdir -p "$(dirname "${OUT}")"

ffmpeg -v error -y -framerate "${FPS}" -i "${FRAMES}/f%04d.png" \
	-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -movflags +faststart "${OUT}-assembly.mp4"
ffmpeg -v error -y -framerate "${FPS}" -i "${FRAMES}/f%04d.png" \
	-vf "fps=12,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=160[p];[b][p]paletteuse=dither=bayer:bayer_scale=3" \
	-loop 0 "${OUT}-assembly.gif"

# the end credits: one tall image scrolling up over black, from just below
# the frame to just above it
HERE=$(cd "$(dirname "$0")" && pwd)
CREDITS=${CREDITS:-${HERE}/credits.txt}
CREDITS_SCREEN=${CREDITS_SCREEN:-5}
W=${SIZE%x*}
H=${SIZE#*x}
TMP=$(mktemp -d)
trap 'rm -rf "${TMP}"' EXIT
python3 "${HERE}/make_credits.py" "${CREDITS}" "${TMP}/credits.png" "${W}" "${H}"
CH=$(ffprobe -v error -show_entries stream=height -of csv=p=0 "${TMP}/credits.png")
SPEED=$(awk "BEGIN{printf \"%.3f\", ${H}/${CREDITS_SCREEN}}")    # px/s
CREDITS_HOLD=${CREDITS_HOLD:-3}
if [ -f "${TMP}/credits.png.stop" ]; then
	# the scrolling stops CREDITS_HOLD s with the logos in the middle
	YS=$(awk "BEGIN{printf \"%.1f\", ${H}/2-$(cat "${TMP}/credits.png.stop")}")
	T1=$(awk "BEGIN{printf \"%.3f\", (${H}-(${YS}))/${SPEED}}")
	T2=$(awk "BEGIN{printf \"%.3f\", ${T1}+${CREDITS_HOLD}}")
	C=$(awk "BEGIN{printf \"%.3f\", ${T2}+((${YS})+${CH})/${SPEED}}")
	SCROLL="if(lt(t,${T1}),H-t*${SPEED},if(lt(t,${T2}),${YS},${YS}-(t-${T2})*${SPEED}))"
else
	C=$(awk "BEGIN{printf \"%.3f\", (${H}+${CH})/${SPEED}}")
	SCROLL="H-t*${SPEED}"
fi
TOTAL=$(awk "BEGIN{printf \"%.3f\", ${D}+${C}+${CARD}}")
FADE_END=$(awk "BEGIN{printf \"%.3f\", ${TOTAL}-${CARD_FADE}}")
echo "credits ${CH} px, ${C} s; teaser ${TOTAL} s"

# the end card: both lines fade in, then out in the last CARD_FADE seconds
esc() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e "s/'/\\\\'/g" -e 's/:/\\:/g' -e 's/%/\\%/g'; }
ALPHA="if(lt(t,0.6),t/0.6,if(lt(t,${CARD}-${CARD_FADE}),1,(${CARD}-t)/${CARD_FADE}))"
TXT="drawtext=fontfile=${FONT}:text='$(esc "${TITLE}")':fontcolor=white:fontsize=h/6.5:x=(w-text_w)/2:y=(h-text_h)/2:alpha='${ALPHA}'"
SUB="drawtext=fontfile=${FONT}:text='$(esc "${SUBTITLE}")':fontcolor=white:fontsize=h/20:x=(w-text_w)/2:y=h-h/9-text_h:alpha='${ALPHA}'"
VIDEO="[0:v]fade=t=out:st=${FADE_AT}:d=1,format=yuv420p,setsar=1[a];\
[2:v][1:v]overlay=x=0:y='${SCROLL}',format=yuv420p,setsar=1[r];\
[3:v]${TXT},${SUB},format=yuv420p,setsar=1[c];\
[a][r][c]concat=n=3:v=1:a=0[v]"
INPUTS=(-framerate "${FPS}" -i "${FRAMES}/f%04d.png"
	-loop 1 -framerate "${FPS}" -t "${C}" -i "${TMP}/credits.png"
	-f lavfi -i "color=c=black:s=${SIZE}:r=${FPS}:d=${C}"
	-f lavfi -i "color=c=black:s=${SIZE}:r=${FPS}:d=${CARD}")
if [ -n "${MUSIC}" ]; then
	AUDIO="[4:a]atrim=${MUSIC_START}:$(awk "BEGIN{print ${MUSIC_START}+${TOTAL}}"),asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,afade=t=in:st=0:d=1.5,afade=t=out:st=${FADE_END}:d=${CARD_FADE},apad[m]"
	ffmpeg -v error -y "${INPUTS[@]}" -i "${MUSIC}" \
		-filter_complex "${VIDEO};${AUDIO}" -map "[v]" -map "[m]" -t "${TOTAL}" \
		-c:v libx264 -preset slow -crf 18 -c:a aac -b:a 192k -movflags +faststart "${OUT}-teaser.mp4"
else
	ffmpeg -v error -y "${INPUTS[@]}" \
		-filter_complex "${VIDEO}" -map "[v]" -t "${TOTAL}" \
		-c:v libx264 -preset slow -crf 18 -movflags +faststart "${OUT}-teaser.mp4"
fi
ls -l "${OUT}"-*

#!/bin/bash
# Publishes a teaser made by tools/make_video.sh, from a GitHub Actions job
# (GH_TOKEN, a checkout that can push, the gh CLI):
#   - ANIMATION and TEASER_ENV (when given) go to the release "teaser-master"
#     as animation.mp4 and teaser.env: the master that credits.yml re-makes
#     the end credits on;
#   - TEASER becomes docs/teaser.mp4 (GitHub Pages), committed and pushed,
#     then a Pages build is requested.
#
# Usage: tools/publish_teaser.sh TEASER.mp4 [ANIMATION.mp4 TEASER_ENV] MESSAGE
set -e -o pipefail
TEASER=${1:?usage: $0 TEASER.mp4 [ANIMATION.mp4 TEASER_ENV] MESSAGE}
if [ $# -ge 4 ]; then
	ANIMATION=$2
	TEASER_ENV=$3
	MESSAGE=$4
else
	MESSAGE=${2:?usage: $0 TEASER.mp4 [ANIMATION.mp4 TEASER_ENV] MESSAGE}
fi
TAG=teaser-master

git config --global --add safe.directory "$(pwd)"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

if [ -n "${ANIMATION}" ]; then
	[ -s "${ANIMATION}" ] && [ -s "${TEASER_ENV}" ] || { echo "missing ${ANIMATION} or ${TEASER_ENV}"; exit 1; }
	TMP=$(mktemp -d)
	trap 'rm -rf "${TMP}"' EXIT
	cp "${ANIMATION}" "${TMP}/animation.mp4"
	cp "${TEASER_ENV}" "${TMP}/teaser.env"
	if ! gh release view "${TAG}" >/dev/null 2>&1; then
		gh release create "${TAG}" --target "$(git rev-parse HEAD)" --title "Teaser master" \
			--notes "The teaser without its end credits (animation.mp4) and its music and card texts (teaser.env), for .github/workflows/credits.yml. Replaced by the Teaser workflow with publish." \
			--prerelease
	fi
	gh release upload "${TAG}" "${TMP}/animation.mp4" "${TMP}/teaser.env" --clobber
	echo "master uploaded to the release ${TAG}"
fi

cp "${TEASER}" docs/teaser.mp4
git add docs/teaser.mp4
if git diff --cached --quiet; then
	echo "docs/teaser.mp4 unchanged"
	exit 0
fi
git commit -q -m "${MESSAGE}"
for i in 1 2 3; do
	git pull -q --rebase origin "${GITHUB_REF_NAME:-master}" && git push -q origin "HEAD:${GITHUB_REF_NAME:-master}" && break
	sleep 5
done
echo "docs/teaser.mp4 published ($(git rev-parse --short HEAD))"
# a push made with the job's token may not start a Pages build by itself
gh api -X POST "repos/${GITHUB_REPOSITORY}/pages/builds" >/dev/null 2>&1 || echo "Pages build not requested (it may start by itself)"

#!/bin/bash
# Runs a program of KiCad 5 (kicad2step, pcbnew, eeschema, ...): the system
# one when the system has KiCad 5 (e.g. Debian 11), otherwise the one inside
# the KiCad 5 AppImage ("kicad5" in the PATH, v2.2.0 or later), started
# through the AppImage's Python so that it gets the AppImage environment.
#
# Usage: run_kicad5.sh PROGRAM [arguments...]
#        run_kicad5.sh --check     exit 0 if a KiCad 5 is available
#
# The system KiCad counts only when its pcbnew Python module is version 5:
# a KiCad 6 or later has other file formats and APIs.

PYTHON_MODULE_PATH="/usr/lib/python3/dist-packages"
PYTHON3=$(which python3)

system_kicad5() {
    PYTHONPATH=$PYTHON_MODULE_PATH ${PYTHON3} -c "import pcbnew, sys; sys.exit(0 if pcbnew.GetBuildVersion().lstrip('(').startswith('5') else 1)" >/dev/null 2>&1
}

if [ "$1" = "--check" ]; then
    system_kicad5 && exit 0
    command -v kicad5 >/dev/null 2>&1 && exit 0
    exit 1
fi
if [ -z "$1" ]; then
    echo "Usage: $0 PROGRAM [arguments...] | --check"
    exit 1
fi

PROG=$1
shift
if system_kicad5 && command -v "$PROG" >/dev/null 2>&1; then
    exec "$PROG" "$@"
elif command -v kicad5 >/dev/null 2>&1; then
    exec kicad5 --python -c 'import os, subprocess, sys
b = os.environ["KICAD_PATH"].replace("share/kicad", "bin")
sys.exit(subprocess.call([os.path.join(b, sys.argv[1])] + sys.argv[2:]))' "$PROG" "$@"
fi
echo "Error: no KiCad 5 found. Install KiCad 5 or put the KiCad 5 AppImage"
echo "(v2.2.0 or later) in the PATH as 'kicad5'."
exit 1

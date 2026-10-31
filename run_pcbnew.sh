#!/bin/bash
# Runs a Python script that needs the KiCad 5 pcbnew module.
#
# The pcbnew module comes from a system KiCad 5 (e.g. Debian 11) when there
# is one, otherwise from the KiCad 5 AppImage ("kicad5 --python", v2.2.0+),
# as in run_generate_cpl.sh.
#
# Usage: run_pcbnew.sh <script.py> [arguments...]

PYTHON_MODULE_PATH="/usr/lib/python3/dist-packages"
PYTHON3=$(which python3)

if [ -z "$1" ]; then
    echo "Usage: $0 <script.py> [arguments...]"
    exit 1
fi

if PYTHONPATH=$PYTHON_MODULE_PATH ${PYTHON3} -c "import pcbnew" >/dev/null 2>&1; then
    exec env PYTHONPATH="$PYTHON_MODULE_PATH" "${PYTHON3}" "$@"
elif command -v kicad5 >/dev/null 2>&1; then
    exec kicad5 --python "$@"
fi
echo "Error: no pcbnew module found. Install KiCad 5 or put the KiCad 5"
echo "AppImage (v2.2.0 or later) in the PATH as 'kicad5'."
exit 1

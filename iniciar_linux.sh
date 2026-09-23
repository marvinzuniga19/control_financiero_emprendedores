#!/usr/bin/env bash
set -e

PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "Python no está instalado o no está en el PATH." >&2
    exit 1
fi

if [ ! -d .venv ]; then
    "$PY" -m venv .venv
fi

source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
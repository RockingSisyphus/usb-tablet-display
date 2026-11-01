#!/bin/sh
# Full gate: workflow validation, project quality, and the behaviour test suite.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
PY=${PYTHON:-python3}

CONFIGS="daemon connect disconnect guard-check display-check status internet install"
fail=0

echo "== validate"
for c in $CONFIGS; do
  if ! PYTHONDONTWRITEBYTECODE=1 "$PY" run.py validate --config "usb_tablet_display/configs/$c.jsonc" >/dev/null 2>&1; then
    echo "FAIL validate $c"
    fail=1
  else
    echo "ok   $c"
  fi
done

echo "== quality-check"
if PYTHONDONTWRITEBYTECODE=1 "$PY" run.py quality-check >/dev/null 2>&1; then
  echo "ok   quality-check"
else
  echo "FAIL quality-check"
  fail=1
fi

echo "== pytest"
if PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest tests/ -q; then
  echo "ok   pytest"
else
  echo "FAIL pytest"
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "GATE FAILED"
  exit 1
fi
echo "GATE PASSED"

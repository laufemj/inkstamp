#!/usr/bin/env bash
# One-time setup on macOS / Linux:  bash setup.sh
# Creates a standalone Python 3.12 env (uv-managed), installs the requirements, downloads the fonts, prints an environment report.
set -euo pipefail
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${LECNOTES_VENV:-$HOME/.lecnotes/venv}"
UV="${UV:-$(command -v uv || true)}"
if [ -z "$UV" ]; then
  echo "uv is not installed. Install it (https://docs.astral.sh/uv/getting-started/installation/), then rerun:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
"$UV" python install 3.12
PY="$VENV/bin/python"
[ -x "$PY" ] || "$UV" venv --python 3.12 --python-preference only-managed --seed "$VENV"
"$UV" pip install --python "$PY" -r "$SKILL/requirements.txt"
"$PY" "$SKILL/scripts/fetch_fonts.py"
"$PY" "$SKILL/scripts/doctor.py"
echo
echo "Done. Python for this skill: $PY"

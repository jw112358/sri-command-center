#!/usr/bin/env bash
# SRI OS Command Center — API setup script
# Run once to create the correct Python 3.11+ venv and install deps.
# Usage: cd sri-command-center-api && bash setup.sh

set -e

echo "==> Finding Python 3.11+..."
PYTHON=""
for candidate in python3.13 python3.12 python3.11; do
  if command -v "$candidate" &>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "ERROR: Python 3.11 or newer not found."
  echo "Install it with: brew install python@3.11"
  exit 1
fi

echo "==> Using: $PYTHON ($($PYTHON --version))"

echo "==> Removing old .venv (if any)..."
rm -rf .venv

echo "==> Creating fresh venv..."
"$PYTHON" -m venv .venv

echo "==> Upgrading pip..."
.venv/bin/pip install --upgrade pip -q

echo "==> Installing dependencies..."
.venv/bin/pip install -r requirements.txt

echo ""
echo "✅  Setup complete!"
echo ""
echo "To start the API server:"
echo "  source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "Or from the repo root:"
echo "  make dev-api"

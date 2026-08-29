#!/usr/bin/env bash
# Set up the Parakeet dictation environment on macOS (Apple Silicon).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "==> Installing portaudio (mic backend for sounddevice)..."
brew list portaudio >/dev/null 2>&1 || brew install portaudio

echo "==> Creating virtualenv (.venv)..."
python3 -m venv .venv
source .venv/bin/activate

echo "==> Upgrading pip..."
pip install --upgrade pip

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo
echo "Done. Test it with:"
echo "    $DIR/.venv/bin/python $DIR/parakeet_dictate.py"
echo
echo "The FIRST run downloads the Parakeet model (~600 MB) and will prompt for"
echo "Microphone + Accessibility permissions. Grant both, then restart it."

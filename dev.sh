#!/usr/bin/env bash
# Dev mode.
#
#   handlers.py  -> HOT-RELOADED in-process (model stays resident, instant).
#   parakeet_dictate.py (core) -> needs a restart; this script does it for you.
#
# So run ./dev.sh, then:
#   - edit handlers.py freely (voice commands, symbols, insertion) -> instant.
#   - edit the core (audio/model/hotkey)  -> full restart (reloads the model).
#
# Only the core file is watched here, so it doesn't fight the warm reload.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PY=".venv/bin/python"

# watchmedo ships with watchdog, a DEV-only dep not in requirements.txt.
if ! "$PY" -c "import watchdog" 2>/dev/null; then
    echo "dev mode needs 'watchdog' (a dev-only dependency). Install it with:" >&2
    echo "    $PY -m pip install watchdog" >&2
    echo "or install all dev extras:  $PY -m pip install -e '.[dev]'" >&2
    exit 1
fi

# Invoke watchmedo via 'python -m', NOT the .venv/bin/watchmedo console script:
# that script's shebang hardcodes an absolute interpreter path that breaks if
# the project directory is renamed. 'python -m' uses the venv's python symlink.
exec "$PY" -m watchdog.watchmedo auto-restart \
    --patterns="parakeet_dictate.py" \
    --signal SIGTERM \
    -- "$PY" parakeet_dictate.py

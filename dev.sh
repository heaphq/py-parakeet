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

exec .venv/bin/watchmedo auto-restart \
    --patterns="parakeet_dictate.py" \
    --signal SIGTERM \
    -- .venv/bin/python parakeet_dictate.py

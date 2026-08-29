# SPDX-FileCopyrightText: 2026 Naval Monga
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hot-reloadable dictation logic: text post-processing + insertion.

The daemon re-imports this module whenever you save it, so you can tweak voice
commands, spoken symbols, and insertion behavior WITHOUT reloading the model.

Keep model/audio/hotkey code in parakeet_dictate.py — those need a full restart.
Anything you edit here takes effect on the next dictation after you save.
"""

import os
import re
import time
import subprocess

from pynput import keyboard

# ---- config (env-overridable) ----
# "paste" (Cmd+V, reliable, preserves clipboard) or "type" (per-char).
INSERT = os.environ.get("PARAKEET_INSERT", "paste").lower()
# Delay between simulated keystrokes in "type" mode (stops dropped characters).
KEY_DELAY = float(os.environ.get("PARAKEET_KEY_DELAY", "0.006"))
# Append a space after each utterance so consecutive dictations don't collide.
TRAILING_SPACE = os.environ.get("PARAKEET_TRAILING_SPACE", "1") == "1"

# Whole-utterance commands: transcript must equal exactly this phrase.
VOICE_COMMANDS = {
    "new line": "\n",
    "new paragraph": "\n\n",
}

# Inline spoken symbols: replaced anywhere, surrounding spaces collapsed
# (so "home slash user" -> "home/user"). Longer phrases first.
INLINE_SYMBOLS = [
    ("forward slash", "/"),
    ("slash", "/"),
]


def post_process(text):
    """Turn a raw transcript into the final string to insert."""
    # 1. Whole-utterance command (you said only "new line").
    low = text.lower().strip(" .")
    if low in VOICE_COMMANDS:
        return VOICE_COMMANDS[low]
    # 2. Inline spoken symbols.
    for phrase, symbol in INLINE_SYMBOLS:
        text = re.sub(
            r"\s*\b" + re.escape(phrase) + r"\b\s*",
            symbol,
            text,
            flags=re.IGNORECASE,
        )
    # 3. Trailing space.
    if TRAILING_SPACE and not text.endswith(("\n", " ")):
        text += " "
    return text


def insert(kb, text):
    """Insert text at the cursor. Raises on failure (caller signals the error)."""
    if INSERT == "type":
        _type(kb, text)
    else:
        _paste(kb, text)


def _paste(kb, text):
    # Stash clipboard, copy text, Cmd+V, then restore the clipboard.
    prev = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
    subprocess.run(["pbcopy"], input=text, text=True)
    kb.press(keyboard.Key.cmd)
    kb.press("v")
    kb.release("v")
    kb.release(keyboard.Key.cmd)
    time.sleep(0.15)  # let the paste land before restoring
    subprocess.run(["pbcopy"], input=prev, text=True)


def _type(kb, text):
    for ch in text:
        kb.type(ch)
        if KEY_DELAY:
            time.sleep(KEY_DELAY)

# Contributing

Thanks for your interest in improving Parakeet Dictation! This is a small,
local-first macOS tool, so contributions are easy to test end to end.

## Development setup

Requirements: Apple Silicon Mac, Homebrew, Python 3.10+.

```bash
git clone https://github.com/heaphq/py-parakeet
cd py-parakeet
./setup.sh                       # portaudio + .venv + deps
.venv/bin/pip install -e ".[dev]"  # editable install + watchdog for dev.sh
```

The first run downloads the model (~600 MB) and prompts for **Microphone** and
**Accessibility** permissions — grant both. See the README for details.

## How the code is organized

Two modules, split by how often you change them:

- **`parakeet_dictate.py`** — the stable core: model loading, audio capture,
  the global hotkey, and the main transcription loop. Editing this needs a
  restart. Run `./dev.sh` to auto-restart it on save.
- **`handlers.py`** — text post-processing and insertion (voice commands,
  spoken symbols, paste/type). This is **hot-reloaded**: save it and the change
  applies on the next dictation, with the model still in memory. Most feature
  work (new voice commands, symbols, formatting) happens here.

Key design note: MLX's compute stream is thread-local, so **all** transcription
runs on the main thread via a job queue. The hotkey callback only records audio
and enqueues it — don't move model calls onto other threads.

## Running and testing

```bash
.venv/bin/python parakeet_dictate.py   # normal run
./dev.sh                               # dev mode (auto-restart core on change)
```

There's no automated test suite yet. Please manually verify your change:

1. Dictate a normal sentence and confirm it inserts correctly.
2. Exercise the specific behavior you touched (e.g. a new voice command).
3. Check the console/log output for errors.

Before opening a PR, make sure the modules at least compile:

```bash
.venv/bin/python -c "import py_compile as c; c.compile('parakeet_dictate.py', doraise=True); c.compile('handlers.py', doraise=True)"
```

Pure logic in `handlers.py` (like `post_process`) is easy to check in isolation:

```bash
.venv/bin/python -c "import handlers; print(repr(handlers.post_process('home slash user')))"
```

## Style

- Follow the surrounding style; keep it plain and readable. PEP 8 spacing.
- Prefer standard library; new runtime dependencies need a good reason (they
  also must be license-compatible with AGPL-3.0 — see below).
- Keep comments about *why*, not *what*. Match the existing comment density.

## Adding common things

- **A voice command** (whole utterance → text): add to `VOICE_COMMANDS` in
  `handlers.py`.
- **A spoken symbol** (inline word → character): add to `INLINE_SYMBOLS`
  (longer phrases first).
- **A config knob**: read it from an environment variable with a sensible
  default, and document it in the README's Configuration table.

## Licensing of contributions

This project is licensed under **AGPL-3.0-or-later**. By submitting a
contribution, you agree that your contribution is licensed under the same terms
(inbound = outbound). Add or keep the SPDX header on any new source file:

```python
# SPDX-FileCopyrightText: <year> <your name>
# SPDX-License-Identifier: AGPL-3.0-or-later
```

Any new dependency must be license-compatible with AGPL-3.0 (MIT, BSD,
Apache-2.0, LGPL/GPL/AGPL are fine; note the license in your PR).

## Pull requests

- Keep PRs focused on one change.
- Describe what you changed, why, and how you tested it on your machine
  (macOS version and chip help).
- Link any related issue.

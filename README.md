# Parakeet Dictation (macOS, Apple Silicon)

System-wide, fully-local voice-to-text using NVIDIA's **Parakeet** model via
[`parakeet-mlx`](https://github.com/senstella/parakeet-mlx). Runs on-device on
Apple Silicon — nothing is sent to the cloud.

**How it works:** press a global hotkey to start recording, press it again to
stop. The audio is transcribed and inserted at your cursor, in any app. Press
**Esc** while recording to cancel and discard it.

- Trigger: **toggle** (press on / press off); **Esc** cancels a recording
- Insert: **clipboard paste** by default (preserves your clipboard); optional
  per-character typing via `PARAKEET_INSERT=type`
- Form: **headless background daemon**
- Default hotkey: **Ctrl + Space**

## Requirements

- **Apple Silicon** Mac (M1 or newer) — `parakeet-mlx` needs MLX/Metal.
- **Homebrew** (for `portaudio`, the microphone backend).
- **Python 3.10+**.

## 1. Install

```bash
git clone https://github.com/heaphq/py-parakeet.git
cd py-parakeet
./setup.sh
```

This installs `portaudio`, creates `.venv`, and installs the Python deps.

<details>
<summary>Alternative: install as a global <code>parakeet-dictate</code> command</summary>

`portaudio` is still required (`brew install portaudio`). Then, with
[uv](https://docs.astral.sh/uv/) (recommended) or pipx:

```bash
uv tool install .        # or: pipx install .
parakeet-dictate         # run from anywhere
```
</details>

## 2. First run (grant permissions)

Run it in Terminal the first time so macOS shows the permission prompts:

```bash
.venv/bin/python parakeet_dictate.py
```

- The first launch **downloads the model (~600 MB)** — wait for `Model ready.`
- macOS will ask for **Microphone** access → Allow.
- Press the hotkey; macOS will ask for **Accessibility** (needed to type
  keystrokes and read the global hotkey) → open
  *System Settings → Privacy & Security → Accessibility* and enable **Terminal**
  (or your terminal app). Then restart the script.

Test: focus any text field, press **Ctrl+Space** (Tink sound), speak, press
it again (Pop sound). Your words appear (Glass sound).

### Sound cues
- **Tink** = recording started
- **Pop** = stopped, transcribing
- **Glass** = text inserted
- **Basso** = nothing heard / error / canceled

### Menu bar icon (optional)
If [`rumps`](https://github.com/jaredgren/rumps) is installed (it's included in
the default install), a menu bar icon shows the current state — ⏳ loading,
🎙️ ready, 🔴 recording, ✍️ transcribing — and offers a **Quit** item. Set
`PARAKEET_MENUBAR=0` to force the old fully-headless behavior; if `rumps` isn't
installed the app runs headless automatically.

## 3. Run at login (background daemon)

Once permissions work in the foreground, install the launch agent:

```bash
# Fill in absolute paths and install
sed "s|__DIR__|$PWD|g" com.parakeet.dictate.plist \
  > ~/Library/LaunchAgents/com.parakeet.dictate.plist

launchctl load ~/Library/LaunchAgents/com.parakeet.dictate.plist
```

Logs go to `dictate.log`. To stop / restart:

```bash
launchctl unload ~/Library/LaunchAgents/com.parakeet.dictate.plist
launchctl load   ~/Library/LaunchAgents/com.parakeet.dictate.plist
```

> **Note:** the daemon runs as your login user, but Accessibility permission is
> tied to the *binary* (`.venv/bin/python`). If typing doesn't work under the
> launch agent, add that exact python binary to Accessibility, or grant your
> terminal and launch it from there.

## Configuration

Environment variables (set them in the plist's `EnvironmentVariables`, or the
shell when running manually):

| Var                      | Default                             | Meaning                                   |
|--------------------------|-------------------------------------|-------------------------------------------|
| `PARAKEET_MODEL`         | `mlx-community/parakeet-tdt-0.6b-v2` | HuggingFace model repo                    |
| `PARAKEET_HOTKEY`        | `<ctrl>+<space>`                    | pynput hotkey string                      |
| `PARAKEET_SOUNDS`        | `1`                                 | `0` to disable system-sound cues          |
| `PARAKEET_MENUBAR`       | `1`                                 | `0` to force headless (no menu bar icon)  |
| `PARAKEET_INSERT`        | `paste`                             | `paste` (Cmd+V) or `type` (per-character) |
| `PARAKEET_KEY_DELAY`     | `0.006`                             | seconds between keystrokes in `type` mode |
| `PARAKEET_TRAILING_SPACE`| `1`                                 | `0` to not append a space per utterance   |

Hotkey syntax examples: `<cmd>+<alt>+space`, `<ctrl>+<shift>+v`. See the
[pynput docs](https://pynput.readthedocs.io/en/latest/keyboard.html#global-hotkeys).

## Customizing & developing

Text post-processing and insertion live in **`handlers.py`**, which is
**hot-reloaded** — edit voice commands, spoken symbols (e.g. "slash" → `/`), or
insertion behavior, save, and it applies on the next dictation without reloading
the model. The stable core (model, audio, hotkey) is in `parakeet_dictate.py`;
run `./dev.sh` to auto-restart it on change.

## Troubleshooting

- **No text typed / hotkey ignored:** Accessibility permission missing for the
  python binary. Fix in Privacy & Security → Accessibility.
- **No audio / immediate Basso:** Microphone permission missing, or wrong input
  device. Check System Settings → Sound → Input.
- **Slow first transcription:** the model warms up on first use; subsequent runs
  are fast.

## License

Copyright (C) 2026 Naval Monga.

This program is free software: you can redistribute it and/or modify it under
the terms of the **GNU Affero General Public License v3.0 or later** (AGPL-3.0).
See [LICENSE](LICENSE) for the full text. It is distributed WITHOUT ANY
WARRANTY.

### Third-party components

This project depends on (but does not redistribute) the following, all of whose
licenses are compatible with AGPL-3.0:

| Component      | License      |
|----------------|--------------|
| parakeet-mlx   | Apache-2.0   |
| pynput         | LGPL-3.0     |
| mlx            | MIT          |
| sounddevice    | MIT          |
| numpy          | BSD-3-Clause |
| rumps          | BSD-3-Clause |

**Model weights** (`mlx-community/parakeet-tdt-0.6b-v2`, derived from NVIDIA's
Parakeet) are downloaded at runtime from Hugging Face and are **not** included
in or covered by this repository's license — they carry their own terms
(NVIDIA's Parakeet is released under CC-BY-4.0). Review the model card before
redistributing or using commercially.

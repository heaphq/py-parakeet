#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Naval Monga
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
System-wide voice-to-text for macOS using NVIDIA Parakeet (via parakeet-mlx).

Toggle-style dictation:
  - Press the hotkey (default Ctrl+Space) to START recording.
  - Press it again to STOP; the audio is transcribed and inserted at the cursor.

Runs headless. Audible cues signal state:
  - Tink  -> started recording
  - Pop   -> stopped, transcribing
  - Glass -> text inserted
  - Basso -> error / nothing heard

Text post-processing and insertion live in handlers.py, which is HOT-RELOADED:
edit and save handlers.py and the change applies on the next dictation, with
the model still resident. Editing THIS file needs a restart.

Config via environment variables:
  PARAKEET_MODEL   HuggingFace repo (default: mlx-community/parakeet-tdt-0.6b-v2)
  PARAKEET_HOTKEY  pynput hotkey string (default: <ctrl>+<space>)
  PARAKEET_SOUNDS  "1" to enable system-sound cues (default: 1)
"""

import os
import sys
import time
import queue
import threading
import importlib

import wave
import tempfile
import subprocess

import numpy as np
import sounddevice as sd
from pynput import keyboard

import handlers  # hot-reloadable text post-processing + insertion logic

SAMPLE_RATE = 16000          # Parakeet expects 16 kHz mono
CHANNELS = 1
MODEL = os.environ.get("PARAKEET_MODEL", "mlx-community/parakeet-tdt-0.6b-v2")
HOTKEY = os.environ.get("PARAKEET_HOTKEY", "<ctrl>+<space>")
SOUNDS = os.environ.get("PARAKEET_SOUNDS", "1") == "1"

SOUND_DIR = "/System/Library/Sounds"


def log(*args):
    print(*args, flush=True)


def cue(name):
    """Play a short macOS system sound as a non-visual status cue."""
    if not SOUNDS:
        return
    path = os.path.join(SOUND_DIR, f"{name}.aiff")
    if os.path.exists(path):
        subprocess.Popen(
            ["afplay", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def watch_handlers(interval=0.5):
    """Re-import handlers.py when it changes, keeping the model resident.

    Syntax-checks first so a bad save can't crash the daemon — on error it
    logs and keeps the last good version loaded.
    """
    path = os.path.abspath(handlers.__file__)
    last = os.path.getmtime(path)
    while True:
        time.sleep(interval)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime == last:
            continue
        last = mtime
        try:
            with open(path) as f:
                compile(f.read(), path, "exec")  # validate before reloading
        except SyntaxError as e:
            log(f"⚠ handlers.py syntax error, not reloaded: {e}")
            continue
        try:
            importlib.reload(handlers)
            log("↻ reloaded handlers.py")
        except Exception as e:
            log(f"⚠ handlers.py reload failed: {e}")


class Dictation:
    def __init__(self):
        self.recording = False
        self.frames = []
        self.stream = None
        self.lock = threading.Lock()
        self.model = None
        self.kb = keyboard.Controller()
        # MLX's compute stream is thread-local, so ALL transcription must run
        # on the same (main) thread. The hotkey callback just enqueues audio.
        self.jobs = queue.Queue()

    def load_model(self):
        from parakeet_mlx import from_pretrained
        log(f"Loading Parakeet model: {MODEL} ...")
        self.model = from_pretrained(MODEL)
        log("Model ready. Press the hotkey to dictate.")

    # ---- audio ----
    def _audio_cb(self, indata, frames, time_info, status):
        if status:
            log(f"audio status: {status}")
        if self.recording:
            self.frames.append(indata.copy())

    def toggle(self):
        # Runs on the hotkey listener thread; keep it quick.
        with self.lock:
            if not self.recording:
                self._start()
            else:
                self._stop()

    def _start(self):
        self.frames = []
        self.recording = True
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=self._audio_cb,
        )
        self.stream.start()
        cue("Tink")
        log("● recording...")

    def _stop(self):
        self.recording = False
        try:
            self.stream.stop()
            self.stream.close()
        finally:
            self.stream = None
        cue("Pop")
        log("■ stopped, transcribing...")
        audio = (
            np.concatenate(self.frames, axis=0)
            if self.frames
            else np.zeros((0, CHANNELS), dtype="float32")
        )
        # Hand off to the main-thread worker (MLX stream is thread-local).
        self.jobs.put(audio)

    def run(self):
        """Main-thread worker loop: transcribe queued audio and insert it."""
        while True:
            audio = self.jobs.get()
            self._transcribe(audio)

    # ---- transcription + insertion ----
    def _transcribe(self, audio):
        if audio.shape[0] < SAMPLE_RATE * 0.3:  # < 0.3s of audio
            log("(too short, ignored)")
            cue("Basso")
            return

        pcm = np.clip(audio[:, 0], -1.0, 1.0)
        pcm16 = (pcm * 32767).astype(np.int16)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            path = tf.name
        try:
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SAMPLE_RATE)
                w.writeframes(pcm16.tobytes())

            result = self.model.transcribe(path)
            text = (result.text or "").strip()
        except Exception as e:
            log(f"transcription error: {e}")
            cue("Basso")
            return
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

        if not text:
            log("(no speech detected)")
            cue("Basso")
            return

        # Hot-reloadable logic lives in handlers.py.
        text = handlers.post_process(text)
        log(f"→ {text!r}")
        try:
            handlers.insert(self.kb, text)
            cue("Glass")
        except Exception as e:
            log(f"insert error: {e}")
            cue("Basso")


def main():
    d = Dictation()
    d.load_model()

    threading.Thread(target=watch_handlers, daemon=True).start()

    listener = keyboard.GlobalHotKeys({HOTKEY: d.toggle})
    listener.start()
    log(f"Hotkey armed: {HOTKEY} (handlers.py hot-reloads on save)")
    d.run()  # blocks on the job queue, on the main thread


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

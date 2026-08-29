#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Naval Monga
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
System-wide voice-to-text for macOS using NVIDIA Parakeet (via parakeet-mlx).

Toggle-style dictation:
  - Press the hotkey (default Ctrl+Space) to START recording.
  - Press it again to STOP; the audio is transcribed and inserted at the cursor.
  - Press Esc while recording to CANCEL (discard without transcribing).

Runs headless. Audible cues signal state:
  - Tink  -> started recording
  - Pop   -> stopped, transcribing
  - Glass -> text inserted
  - Basso -> error / nothing heard / canceled

If `rumps` is installed, a menu bar icon also shows the current state and
offers a Quit item; without it, the daemon runs fully headless as before.

Text post-processing and insertion live in handlers.py, which is HOT-RELOADED:
edit and save handlers.py and the change applies on the next dictation, with
the model still resident. Editing THIS file needs a restart.

Config via environment variables:
  PARAKEET_MODEL    HuggingFace repo (default: mlx-community/parakeet-tdt-0.6b-v2)
  PARAKEET_HOTKEY   pynput hotkey string (default: <ctrl>+<space>)
  PARAKEET_SOUNDS   "1" to enable system-sound cues (default: 1)
  PARAKEET_MENUBAR  "1" to show the menu bar icon when rumps is installed (default: 1)
"""

import os
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

try:
    import rumps  # optional: macOS menu bar indicator
except ImportError:
    rumps = None

SAMPLE_RATE = 16000  # Parakeet expects 16 kHz mono
CHANNELS = 1
MODEL = os.environ.get("PARAKEET_MODEL", "mlx-community/parakeet-tdt-0.6b-v2")
HOTKEY = os.environ.get("PARAKEET_HOTKEY", "<ctrl>+<space>")
CANCEL_KEY = "<esc>"  # press while recording to discard
SOUNDS = os.environ.get("PARAKEET_SOUNDS", "1") == "1"
MENUBAR = os.environ.get("PARAKEET_MENUBAR", "1") == "1"

SOUND_DIR = "/System/Library/Sounds"

# Menu bar icons per state (see Dictation.state).
STATE_ICONS = {
    "loading": "⏳",
    "ready": "🎙️",
    "recording": "🔴",
    "transcribing": "✍️",
}


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
        # Coarse status for the menu bar; a plain string is fine to read across
        # threads (updates are atomic and the menu bar only polls it).
        self.state = "loading"
        # MLX's compute stream is thread-local, so the model must be loaded and
        # used on ONE thread (the worker); the hotkey callback just enqueues
        # audio. When the menu bar runs, that worker is a background thread so
        # rumps can own the main run loop.
        self.jobs = queue.Queue()

    def load_model(self):
        from parakeet_mlx import from_pretrained

        log(f"Loading Parakeet model: {MODEL} ...")
        self.model = from_pretrained(MODEL)
        self.state = "ready"
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

    def cancel(self):
        """Discard an in-progress recording without transcribing.

        Bound to Esc; a no-op (and harmless) when not recording, so it never
        interferes with normal Escape presses.
        """
        with self.lock:
            if not self.recording:
                return
            self._close_stream()
            self.frames = []
            self.state = "ready"
            cue("Basso")
            log("✕ canceled")

    def _close_stream(self):
        self.recording = False
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
        finally:
            self.stream = None

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
        self.state = "recording"
        cue("Tink")
        log("● recording...")

    def _stop(self):
        self._close_stream()
        self.state = "transcribing"
        cue("Pop")
        log("■ stopped, transcribing...")
        audio = (
            np.concatenate(self.frames, axis=0)
            if self.frames
            else np.zeros((0, CHANNELS), dtype="float32")
        )
        # Hand off to the worker (MLX stream is thread-local).
        self.jobs.put(audio)

    def worker(self):
        """Worker loop: load the model, then transcribe queued audio.

        Loading and transcribing happen on this one thread to satisfy MLX's
        thread-local compute stream. Runs on the main thread when headless, or
        on a background thread when the menu bar owns the main run loop.
        """
        self.load_model()
        while True:
            audio = self.jobs.get()
            try:
                self._transcribe(audio)
            finally:
                self.state = "ready"

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


if rumps is not None:

    class MenuBarApp(rumps.App):
        """Menu bar icon reflecting the daemon's state.

        Polls d.state on the main run loop (via rumps.Timer) rather than having
        worker threads touch AppKit — cross-thread UI mutation is unsafe.
        """

        def __init__(self, dictation):
            super().__init__(STATE_ICONS["loading"], quit_button="Quit")
            self.d = dictation
            self._timer = rumps.Timer(self._tick, 0.3)
            self._timer.start()

        def _tick(self, _):
            self.title = STATE_ICONS.get(self.d.state, STATE_ICONS["ready"])


def _start_common(d):
    """Wire up hot-reload watching and the global hotkeys."""
    threading.Thread(target=watch_handlers, daemon=True).start()
    listener = keyboard.GlobalHotKeys({HOTKEY: d.toggle, CANCEL_KEY: d.cancel})
    listener.start()
    log(f"Hotkey armed: {HOTKEY} (Esc cancels; handlers.py hot-reloads on save)")


def main():
    d = Dictation()

    if rumps is not None and MENUBAR:
        _start_common(d)
        # Worker (model load + transcription) runs off-main so rumps can own
        # the main run loop; both still happen on that one worker thread.
        threading.Thread(target=d.worker, daemon=True).start()
        MenuBarApp(d).run()
    else:
        _start_common(d)
        d.worker()  # blocks on the job queue, on the main thread


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

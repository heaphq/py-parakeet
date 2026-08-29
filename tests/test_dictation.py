# SPDX-FileCopyrightText: 2026 Naval Monga
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the state machine + menu bar data path in parakeet_dictate.

No model, real audio, or GUI here: sounddevice's InputStream, the sound cue,
and pynput's Controller are all stubbed, so these run fast and headless in CI.
They cover the state transitions the menu bar renders and the icon it maps them
to — the parts of the menu bar feature that don't need a running run loop.
"""

import pytest

import parakeet_dictate as pd


@pytest.fixture
def d(monkeypatch):
    # Keep construction and transitions free of side effects (no afplay
    # subprocess, no pynput controller init that could need permissions).
    monkeypatch.setattr(pd, "cue", lambda *a, **k: None)
    monkeypatch.setattr(pd.keyboard, "Controller", lambda: object())
    return pd.Dictation()


class _FakeStream:
    """Stand-in for sounddevice.InputStream; records lifecycle calls."""

    def __init__(self, *a, **k):
        self.started = self.stopped = self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


# ---- icon mapping (what the menu bar renders) ----


def test_icon_for_known_states():
    for state in ("loading", "ready", "recording", "transcribing"):
        assert pd.icon_for(state) == pd.STATE_ICONS[state]


def test_icon_for_unknown_falls_back_to_ready():
    assert pd.icon_for("bogus") == pd.STATE_ICONS["ready"]


def test_every_settable_state_has_an_icon():
    # Guards against a state string the code sets but the icon map lacks.
    for state in ("loading", "ready", "recording", "transcribing"):
        assert state in pd.STATE_ICONS


# ---- state notifications (what drives the menu bar) ----


def test_set_state_updates_and_notifies(d):
    seen = []
    d.on_state = seen.append
    d._set_state("recording")
    assert d.state == "recording"
    assert seen == ["recording"]


def test_set_state_without_observer_is_safe(d):
    d.on_state = None
    d._set_state("ready")  # must not raise
    assert d.state == "ready"


def test_initial_state_is_loading(d):
    assert d.state == "loading"


# ---- toggle / cancel transitions ----


def test_toggle_start_then_stop_drives_states_and_enqueues(d, monkeypatch):
    fake = _FakeStream()
    monkeypatch.setattr(pd.sd, "InputStream", lambda *a, **k: fake)
    seen = []
    d.on_state = seen.append

    d.toggle()  # start
    assert d.recording is True
    assert d.state == "recording"
    assert fake.started

    d.toggle()  # stop
    assert d.recording is False
    assert d.state == "transcribing"
    assert fake.stopped and fake.closed
    assert d.jobs.qsize() == 1  # audio handed off to the worker
    assert seen == ["recording", "transcribing"]


def test_cancel_while_idle_is_a_noop(d):
    seen = []
    d.on_state = seen.append
    d.cancel()  # not recording
    assert d.state == "loading"  # unchanged from init
    assert seen == []


def test_cancel_while_recording_resets_and_discards(d, monkeypatch):
    fake = _FakeStream()
    monkeypatch.setattr(pd.sd, "InputStream", lambda *a, **k: fake)

    d.toggle()  # start recording
    d.frames = [object()]  # pretend some audio was captured
    d.cancel()

    assert d.recording is False
    assert d.state == "ready"
    assert d.frames == []  # discarded, not transcribed
    assert d.jobs.qsize() == 0  # nothing handed to the worker
    assert fake.stopped and fake.closed

# SPDX-FileCopyrightText: 2026 Naval Monga
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the hot-reloadable text logic in handlers.py.

These cover pure post-processing only — no model, audio, or keystrokes — so
they run fast and headless in CI.
"""

import handlers


def test_voice_command_newline():
    assert handlers.post_process("new line") == "\n"


def test_voice_command_new_paragraph_ignores_case_and_punctuation():
    assert handlers.post_process("New paragraph.") == "\n\n"


def test_inline_slash_collapses_spaces():
    assert handlers.post_process("home slash user") == "home/user "


def test_forward_slash_phrase_matches_before_slash():
    assert handlers.post_process("go forward slash now") == "go/now "


def test_inline_symbol_is_case_insensitive():
    assert handlers.post_process("HOME SLASH USER") == "HOME/USER "


def test_trailing_space_is_added():
    assert handlers.post_process("hello world") == "hello world "


def test_no_double_trailing_space():
    # Already ends in a space -> not doubled.
    assert handlers.post_process("hello ") == "hello "


def test_plain_text_unchanged_except_trailing_space():
    assert handlers.post_process("just a normal sentence") == "just a normal sentence "

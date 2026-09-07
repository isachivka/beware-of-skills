#!/usr/bin/env python3
"""Tests for the local patches carried on top of the upstream recipe.

Upstream refuses to type whenever the composer shows anything it does not recognise as
empty. Claude Code draws a greyed suggestion into an idle composer that reads exactly like
typed text, so a peer message could not be delivered at all until the suggestion happened
to clear — the failure seen as "target composer contains text; nothing was typed after 5
attempts". A real draft must still be refused, which is what upstream's own tests pin.
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    tmp = os.path.join(tempfile.mkdtemp(), "peer_chat_mod.py")
    shutil.copy(os.path.join(HERE, "peer-chat.py"), tmp)
    spec = importlib.util.spec_from_file_location("peer_chat_mod", tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["peer_chat_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


PC = load()
CLAUDE = PC.Profile(pane="left", agent="claude", command="claude",
                    label="Chat from Codex: ", submit="\n")
CODEX = PC.Profile(pane="right", agent="codex", command="codex",
                   label="Chat from Claude: ", submit="\t")
RULE = "─" * 40


class SuggestionProbeTests(unittest.TestCase):
    def test_suggestion_clears_under_a_space(self):
        typed = []
        with patch.dict(PC.suggestion_probe.__globals__, {
            "type_text": Mock(side_effect=lambda s, p, t, w=None: typed.append(t)),
            "pane_text": Mock(return_value=f"{RULE}\n❯ \n{RULE}"),
            "time": Mock(sleep=Mock()),
        }):
            self.assertTrue(PC.suggestion_probe("sid", CLAUDE, PC.EMPTY_CURSOR_COLUMN))
        self.assertEqual(typed, [" ", "\x7f"], "the probe must undo itself")

    def test_draft_survives_the_space(self):
        typed = []
        with patch.dict(PC.suggestion_probe.__globals__, {
            "type_text": Mock(side_effect=lambda s, p, t, w=None: typed.append(t)),
            "pane_text": Mock(return_value=f"{RULE}\n❯  existing draft\n{RULE}"),
            "time": Mock(sleep=Mock()),
        }):
            self.assertFalse(PC.suggestion_probe("sid", CLAUDE, PC.EMPTY_CURSOR_COLUMN))
        self.assertEqual(typed, [" ", "\x7f"], "the draft must be restored either way")

    def test_caret_away_from_home_is_never_probed(self):
        type_text = Mock()
        with patch.dict(PC.suggestion_probe.__globals__, {"type_text": type_text}):
            self.assertFalse(PC.suggestion_probe("sid", CLAUDE, 12))
        type_text.assert_not_called()

    def test_codex_is_probed_too(self):
        typed = []
        with patch.dict(PC.suggestion_probe.__globals__, {
            "type_text": Mock(side_effect=lambda s, p, t, w=None: typed.append(t)),
            "pane_text": Mock(return_value="\u203a  \n  gpt-6-astra high \u00b7 ~/x"),
            "time": Mock(sleep=Mock()),
        }):
            self.assertTrue(PC.suggestion_probe("sid", CODEX, PC.EMPTY_CURSOR_COLUMN))
        self.assertEqual(typed, [" ", "\x7f"])

    def test_probe_failure_reads_as_draft(self):
        with patch.dict(PC.suggestion_probe.__globals__, {
            "type_text": Mock(side_effect=RuntimeError("agtermctl died")),
            "time": Mock(sleep=Mock()),
        }):
            self.assertFalse(PC.suggestion_probe("sid", CLAUDE, PC.EMPTY_CURSOR_COLUMN))


class CodexPlaceholderTests(unittest.TestCase):
    """A 44-column split renders `› Ask Codex to do any`, and equality read that as a draft."""

    def test_truncated_placeholder_is_empty(self):
        for shown in ("Ask Codex to do anything", "Ask Codex to do any",
                      "Ask Codex to do anyth…", "Ask Codex to"):
            self.assertTrue(PC.composer_is_empty(CODEX, shown), shown)

    def test_a_draft_is_not_a_placeholder(self):
        for shown in ("Ask Cod", "one tail to remove", "Ask Codex to do anything else",
                      "please review the diff"):
            self.assertFalse(PC.composer_is_empty(CODEX, shown), shown)

    def test_claude_is_unaffected(self):
        self.assertFalse(PC.composer_is_empty(CLAUDE, "Ask Codex to do any"))
        self.assertTrue(PC.composer_is_empty(CLAUDE, ""))


DRAFT_SCREEN = (
    "─────\x1b[0m\r\n❯\xa0настоящий черновик\r\n"
    "\x1b[0m\x1b[38;2;136;136;136m─────\x1b[0m\r\n\x1b[72;21H"
)
SUGGESTION_SCREEN = (
    "─────\x1b[0m\r\n❯ \x1b[0m\x1b[2mубери /__swap-probe из импла\x1b[0m\r\n"
    "\x1b[0m\x1b[38;2;136;136;136m─────\x1b[0m\r\n\x1b[72;3H"
)
CODEX_SUGGESTION_SCREEN = (
    "\x1b[0m\x1b[1m\x1b[48;2;72;72;72m›\x1b[0m\x1b[48;2;72;72;72m "
    "\x1b[0m\x1b[2m\x1b[48;2;72;72;72mAsk Codex to do any\x1b[0m\r\n\x1b[73;3H"
)


class LiveScreenTests(unittest.TestCase):
    """agterm's live sessions keep every pane in a zmx daemon whose `history --vt` carries
    the styling, which is what tells a suggestion from a draft without touching the pane."""

    def test_dim_row_is_a_suggestion(self):
        self.assertTrue(PC.composer_row_is_dim(SUGGESTION_SCREEN, CLAUDE))
        self.assertTrue(PC.composer_row_is_dim(CODEX_SUGGESTION_SCREEN, CODEX))

    def test_plain_row_is_a_draft(self):
        self.assertFalse(PC.composer_row_is_dim(DRAFT_SCREEN, CLAUDE))

    def test_cursor_comes_out_of_the_stream(self):
        self.assertEqual(PC.zmx_cursor_column(DRAFT_SCREEN), 20)
        self.assertEqual(PC.zmx_cursor_column(SUGGESTION_SCREEN), 2)
        self.assertIsNone(PC.zmx_cursor_column("no report here"))

    def test_probe_prefers_the_screen_over_a_keystroke(self):
        type_text = Mock()
        with patch.dict(PC.suggestion_probe.__globals__, {
            "zmx_screen": Mock(return_value=SUGGESTION_SCREEN),
            "type_text": type_text,
        }):
            self.assertTrue(PC.suggestion_probe("sid", CLAUDE, PC.EMPTY_CURSOR_COLUMN))
        type_text.assert_not_called()

    def test_no_daemon_falls_back_to_the_keystroke(self):
        typed = []
        with patch.dict(PC.suggestion_probe.__globals__, {
            "zmx_screen": Mock(return_value=None),
            "type_text": Mock(side_effect=lambda s, p, t, w=None: typed.append(t)),
            "pane_text": Mock(return_value="❯ "),
            "time": Mock(sleep=Mock()),
        }):
            self.assertTrue(PC.suggestion_probe("sid", CLAUDE, PC.EMPTY_CURSOR_COLUMN))
        self.assertEqual(typed, [" ", "\x7f"])


class RefusalDiagnosticsTests(unittest.TestCase):
    def test_refusal_quotes_the_pane(self):
        tail = PC.describe_tail("one\n\ntwo\nthree")
        self.assertIn("three", tail)
        self.assertIn("pane tail:", tail)

    def test_empty_pane_says_so(self):
        self.assertIn("read back empty", PC.describe_tail("   \n\n"))


if __name__ == "__main__":
    unittest.main(verbosity=1)

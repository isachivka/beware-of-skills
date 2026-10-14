"""Tests for the LOCAL PATCH additions on top of the vendored upstream peer-chat.py."""

import importlib.util
import os
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location("peer_chat", os.path.join(HERE, "peer-chat.py"))
peer_chat = importlib.util.module_from_spec(SPEC)
sys.modules["peer_chat"] = peer_chat  # dataclasses resolve annotations through sys.modules
SPEC.loader.exec_module(peer_chat)
CODEX = peer_chat.PROFILES["codex"]
CLAUDE = peer_chat.PROFILES["claude"]


class TruncatedPlaceholderTests(unittest.TestCase):
    def test_truncated_placeholder_counts_as_empty(self) -> None:
        for shown in ("Ask Codex to do any", "Ask Codex to do any…", "Ask Codex⠁to do", "Ask Codex"):
            self.assertTrue(peer_chat.composer_is_empty(CODEX, shown), shown)

    def test_short_or_diverging_text_is_a_draft(self) -> None:
        for shown in ("Ask Cod", "Ask Codex to do anything!", "Ask Codex to do nothing", "Chat from Claude: ping", ""):
            self.assertFalse(peer_chat.composer_is_empty(CODEX, shown), shown)

    def test_full_placeholder_still_empty(self) -> None:
        self.assertTrue(peer_chat.composer_is_empty(CODEX, peer_chat.CODEX_EMPTY_PROMPT))


class RefusalDiagnosticsTests(unittest.TestCase):
    def test_describe_tail_quotes_last_rows(self) -> None:
        pane = "one\n\ntwo\nthree\nfour\nfive\n"
        self.assertEqual(peer_chat.describe_tail(pane), "; pane tail: two | three | four | five")

    def test_describe_tail_empty_pane(self) -> None:
        self.assertEqual(peer_chat.describe_tail(""), "; the pane read back empty")

    def test_unrecognisable_prompt_refusal_carries_the_tail(self) -> None:
        pane = "some output\n! shell mode\n"
        with patch.object(peer_chat, "pane_text", return_value=pane), \
             patch.object(peer_chat, "live_prompt_text", return_value=None):
            with self.assertRaises(peer_chat.PromptBlocked) as ctx:
                peer_chat._send_visible("sid", CODEX, "hi", "hi")
        self.assertIn("pane tail: some output | ! shell mode", str(ctx.exception))


class PaneReachableTests(unittest.TestCase):
    def test_hidden_right_split_is_shown_then_collapsed(self) -> None:
        calls = []
        with patch.object(peer_chat, "find_node", return_value={"hasSplit": True, "split": None}), \
             patch.object(peer_chat, "ctl", side_effect=lambda *a, **k: calls.append(a) or ""):
            with peer_chat.pane_reachable("sid", CODEX) as unhidden:
                self.assertTrue(unhidden)
                self.assertEqual(calls[-1][:4], ("session", "split", "visibility", "on"))
        self.assertEqual(calls[-1][:4], ("session", "split", "visibility", "off"))

    def test_visible_split_is_left_alone(self) -> None:
        calls = []
        with patch.object(peer_chat, "find_node", return_value={"hasSplit": True, "split": {"id": "x"}}), \
             patch.object(peer_chat, "ctl", side_effect=lambda *a, **k: calls.append(a) or ""):
            with peer_chat.pane_reachable("sid", CODEX) as unhidden:
                self.assertFalse(unhidden)
        self.assertEqual(calls, [])

    def test_left_pane_never_toggles(self) -> None:
        calls = []
        with patch.object(peer_chat, "find_node", return_value={"hasSplit": True, "split": None}), \
             patch.object(peer_chat, "ctl", side_effect=lambda *a, **k: calls.append(a) or ""):
            with peer_chat.pane_reachable("sid", CLAUDE) as unhidden:
                self.assertFalse(unhidden)
        self.assertEqual(calls, [])

    def test_find_node_failure_falls_back_to_plain_send(self) -> None:
        with patch.object(peer_chat, "find_node", side_effect=RuntimeError("no node")):
            with peer_chat.pane_reachable("sid", CODEX) as unhidden:
                self.assertFalse(unhidden)


class ScrolledComposerTests(unittest.TestCase):
    """A long message scrolls Codex's composer, which marks its top row with an arrow."""

    SCREEN = "\n".join([
        "  Worked for 28s",
        "",
        "› rounds the font size and :241 takes the min y; :319 switches LH between one line\u2191",
        "  and several. I accept all seven points. [peer-check:0]",
        "",
        "  GPT-6-Astra medium · ~/x",
        "                                                         ⚠ 1 warning · f2 to view",
    ])

    def test_the_scroll_arrow_is_not_text(self) -> None:
        self.assertEqual(
            peer_chat.codex_live_prompt_text(self.SCREEN),
            "rounds the font size and :241 takes the min y; :319 switches LH between one line\n"
            "and several. I accept all seven points. [peer-check:0]",
        )

    def test_a_scrolled_tail_confirms_the_chunk(self) -> None:
        sent = ("Earlier text that scrolled away. I checked: layout.ts:204 "
                "rounds the font size and :241 takes the min y; :319 switches LH between one line "
                "and several. I accept all seven points.")
        content = peer_chat.codex_live_prompt_text(self.SCREEN)
        self.assertTrue(peer_chat.composer_has_expected_tail(content, sent + " [peer-check:0]", " I accept all seven points. [peer-check:0]", True))


class CombiningMarkTests(unittest.TestCase):
    """Text with combining marks is drawn out of step with the cells the read-back counts."""

    def test_marks_that_fold_are_folded(self) -> None:
        self.assertEqual(peer_chat.normalize(CODEX, "Cafe\u0301 I\u0307"), "Chat from Claude: Caf\u00e9 \u0130")

    def test_marks_that_do_not_fold_are_written_out(self) -> None:
        self.assertEqual(peer_chat.normalize(CLAUDE, "i\u0307stanbul"), "Chat from Codex: i\\u0307stanbul")
        self.assertEqual(peer_chat.normalize(CODEX, "a \u0301 b"), "Chat from Claude: a \\u0301 b")
        hindi = "\u0939\u093f\u0928\u094d\u0926\u0940"  # vowel signs and the virama are marks
        self.assertEqual(peer_chat.normalize(CODEX, hindi), "Chat from Claude: \u0939\\u093f\u0928\\u094d\u0926\\u0940")

    def test_plain_text_is_unchanged(self) -> None:
        self.assertEqual(peer_chat.normalize(CODEX, "ёлка «x» 😀 中文"), "Chat from Claude: ёлка «x» 😀 中文")


if __name__ == "__main__":
    unittest.main()

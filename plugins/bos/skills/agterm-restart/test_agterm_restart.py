import importlib.machinery
import os

os.environ.setdefault("AGTERM_SOCKET", "/dev/null")
mod = importlib.machinery.SourceFileLoader(
    "agterm_restart", os.path.join(os.path.dirname(__file__), "agterm-restart")).load_module()

SID = "0d7fc1de-bc54-4ef1-9dfd-c2a7811b56eb"


def test_resume_id_from_exit_screen():
    text = ("Resume this session with:\nclaude --resume %s\n"
            "➜  pdffiller-knowledge-1880 git:(pr-1880)" % SID)
    assert mod.resume_id_from_screen(text) == SID


def test_resume_id_takes_the_last_one():
    old = "edee0412-3a36-4f51-8cf8-a817c9d01ff2"
    assert mod.resume_id_from_screen("claude --resume %s\n...\nclaude --resume %s" % (old, SID)) == SID


def test_resume_id_missing():
    assert mod.resume_id_from_screen("➜  ~") is None


def test_plain_claude_keeps_flags_and_replaces_resume():
    argv = mod.claude_argv(["claude", "--dangerously-skip-permissions", "--resume",
                            "edee0412-3a36-4f51-8cf8-a817c9d01ff2"])
    assert mod.resume_cmd(argv, SID) == "claude --resume %s --dangerously-skip-permissions" % SID


def test_prompt_positional_is_dropped():
    argv = mod.claude_argv(["claude", "--dangerously-skip-permissions", "# Task: it's long\n..."])
    assert mod.resume_cmd(argv, SID) == "claude --resume %s --dangerously-skip-permissions" % SID


def test_duplicate_flags_collapse():
    argv = mod.claude_argv(["claude", "--dangerously-skip-permissions",
                            "--dangerously-skip-permissions"])
    assert mod.resume_cmd(argv, SID) == "claude --resume %s --dangerously-skip-permissions" % SID


def test_value_flags_survive():
    argv = mod.claude_argv(["claude", "--model", "opus", "--add-dir", "/tmp/x y"])
    assert mod.resume_cmd(argv, SID) == "claude --resume %s --model opus --add-dir '/tmp/x y'" % SID


def test_zsh_wrapper_is_recognised():
    argv = mod.claude_argv(["zsh", "-lc", 'claude --dangerously-skip-permissions '
                            '"$(cat ~/.ideas-brief-023.md)"; exec zsh -l'])
    assert mod.resume_cmd(argv, SID) == "claude --resume %s --dangerously-skip-permissions" % SID


def test_versioned_binary_is_claude():
    assert mod.claude_argv(["/Users/is/.local/share/claude/versions/2.1.280", "-c"]) == ["claude", "-c"]


def test_non_claude_panes_are_ignored():
    assert mod.claude_argv(["codex", "--dangerously-bypass-approvals-and-sandbox"]) is None
    assert mod.claude_argv(["zsh", "-lc", "make test"]) is None
    assert mod.claude_argv(None) is None


def test_ready_prompt_with_nbsp():
    screen = "────\n❯\xa0\n────\n  ⏵⏵ bypass permissions on"
    assert mod.READY_RE.search(screen)
    assert not mod.READY_RE.search("Resume full session as-is\nEnter to confirm")

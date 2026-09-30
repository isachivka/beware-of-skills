import json

import pytest

from conftest import REPO, git, repo_dir, write
from ownpr import cli


def own(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_start_uses_repo_default(cfg, checkout, capsys, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "c1")
    monkeypatch.setenv("AGTERM_SESSION_ID", "A1")
    code, out, _ = own(capsys, "start")
    assert code == 0 and "profile full (repo default)" in out
    run = cli.open_journal().open_runs()[0]
    assert (run["claude_session"], run["agterm_session"]) == ("c1", "A1")


def test_start_twice_fails(cfg, checkout, capsys):
    own(capsys, "start")
    code, _, err = own(capsys, "start")
    assert code == 2 and "already exists" in err


def test_start_auto_lists_profiles(cfg, checkout, capsys):
    write(repo_dir(cfg) / "repo.md", "requires: review, ci\ndefault: auto\n")
    code, _, err = own(capsys, "start")
    assert code == 2
    assert "full: runtime change" in err and "quick: small fix" in err
    code, out, _ = own(capsys, "start", "--profile", "quick", "--auto-reason", "one-line fix")
    assert code == 0
    assert cli.open_journal().open_owed()[0]["text"] == "profile quick chosen by the agent: one-line fix"


def test_start_unknown_profile(cfg, checkout, capsys):
    code, _, err = own(capsys, "start", "--profile", "nope")
    assert code == 2 and "no valid profile 'nope'" in err


def test_start_origin_from_root(cfg, checkout, capsys):
    write(cfg / "origins" / "wso.md",
          "root: %s\nstamp: 🤖 WS\nprofile.%s: quick\n" % (checkout, REPO))
    code, out, _ = own(capsys, "start")
    assert "profile quick (origin)" in out and "origin wso" in out


def test_start_bad_mode_env(cfg, checkout, capsys, monkeypatch):
    monkeypatch.setenv("OWN_PR_MODE", "sleepy")
    code, _, err = own(capsys, "start")
    assert code == 2 and "OWN_PR_MODE" in err


def test_next_prints_step_prose_and_context(cfg, checkout, capsys):
    write(cfg / "origins" / "wso.md", "root: %s\nstamp: 🤖 WS\n" % checkout)
    own(capsys, "start")
    own(capsys, "bind", "https://github.com/pdffiller/jsfiller/pull/13300")
    code, out, _ = own(capsys, "next")
    assert code == 0
    assert out.splitlines()[0] == "NEXT: do pr-draft  (kind=auto, mode=attended)"
    assert "PR: https://github.com/pdffiller/jsfiller/pull/13300" in out
    assert "Stamp: 🤖 WS" in out
    assert out.rstrip().endswith("Do pr-draft.")






def test_next_shows_existing_evidence(cfg, checkout, capsys):
    own(capsys, "start")
    own(capsys, "step", "pr-draft", "running", "--evidence", "https://x/1")
    code, out, _ = own(capsys, "next")
    assert "NEXT: reconcile pr-draft" in out
    assert "Evidence so far: https://x/1" in out


def test_bind_rejects_other_repo(cfg, checkout, capsys):
    own(capsys, "start")
    code, _, err = own(capsys, "bind", "https://github.com/pdffiller/pdffiller/pull/5")
    assert code == 2 and "belongs to github.com/pdffiller/pdffiller" in err


def test_unwritable_state_is_an_error_not_a_traceback(cfg, checkout, capsys, monkeypatch, tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    monkeypatch.setenv("OWN_PR_STATE_DIR", str(blocker / "state"))
    code, _, err = own(capsys, "start")
    assert code == 2 and err.startswith("own-pr: ")


def test_owe_and_clear(cfg, checkout, capsys):
    own(capsys, "start")
    own(capsys, "owe", "look at the retry logic")
    owed = cli.open_journal().open_owed()[0]
    assert own(capsys, "clear", str(owed["id"]), "--by-igor")[0] == 0
    assert cli.open_journal().open_owed() == []




def test_machine_away_reports_pinned_runs(cfg, checkout, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("OWN_PR_MODE", "attended")
    own(capsys, "start")
    code, out, _ = own(capsys, "away")
    assert code == 0
    assert open(str(tmp_path / "state" / "mode")).read().strip() == "away"
    assert "stays attended (terminal OWN_PR_MODE)" in out


def test_run_mode_override(cfg, checkout, capsys):
    own(capsys, "start")
    own(capsys, "mode", "away")
    assert cli.open_journal().open_runs()[0]["mode_run"] == "away"
    own(capsys, "mode", "clear")
    assert cli.open_journal().open_runs()[0]["mode_run"] is None


def test_env_claim_between_runs(cfg, checkout, capsys):
    own(capsys, "start")
    assert own(capsys, "env", "claim", "rc09")[0] == 0
    git(checkout, "checkout", "-q", "-b", "feature/other")
    own(capsys, "start")
    code, _, err = own(capsys, "env", "claim", "rc09")
    assert code == 2 and "rc09 is claimed by run" in err


def test_close_refuses_running(cfg, checkout, capsys):
    own(capsys, "start")
    own(capsys, "step", "ci", "running")
    code, _, err = own(capsys, "close")
    assert code == 2 and "ci is running" in err
    own(capsys, "step", "ci", "done")
    assert own(capsys, "close")[0] == 0
    code, _, err = own(capsys, "next")
    assert code == 2 and "no open run" in err


def test_profile_switch(cfg, checkout, capsys):
    own(capsys, "start")
    code, out, _ = own(capsys, "profile", "quick", "--by-igor")
    assert code == 0 and "removed: decomment, deploy-rc" in out


def test_explain(cfg, checkout, capsys):
    write(repo_dir(cfg) / "profiles" / "bad.md", "description: d\nsteps: pr-draft, nope\n")
    own(capsys, "start")
    code, out, _ = own(capsys, "explain")
    assert code == 0
    assert "repo: github.com/pdffiller/jsfiller" in out
    assert "profile: full (repo default)" in out
    assert "mode: attended (default)" in out
    assert "eyeball  kind=human away=defer" in out
    assert "invalid profile bad: unknown step 'nope'" in out


def test_explain_without_run(cfg, checkout, capsys):
    code, out, _ = own(capsys, "explain")
    assert code == 0 and "profiles: full, quick" in out


def test_adopt(cfg, checkout, capsys, monkeypatch):
    own(capsys, "start")
    rid = cli.open_journal().open_runs()[0]["id"]
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "c2")
    assert own(capsys, "adopt", rid)[0] == 0
    assert cli.open_journal().run(rid)["claude_session"] == "c2"


def test_export(cfg, checkout, capsys):
    own(capsys, "start")
    code, out, _ = own(capsys, "export")
    assert json.loads(out)["runs"][0]["profile"] == "full"


def test_no_config_for_repo(cfg, checkout, capsys):
    git(checkout, "remote", "set-url", "origin", "git@github.com:someone/else.git")
    code, _, err = own(capsys, "start")
    assert code == 2 and err.startswith("own-pr: no own-pr config for github.com/someone/else")


def test_clear_needs_by_igor(cfg, checkout, capsys):
    own(capsys, "start")
    own(capsys, "owe", "look at it")
    owed = cli.open_journal().open_owed()[0]["id"]
    code, _, err = own(capsys, "clear", str(owed))
    assert code == 2 and "only Igor" in err
    assert cli.open_journal().open_owed()[0]["id"] == owed


def test_non_utf8_config_is_an_error_not_a_traceback(cfg, checkout, capsys):
    (cfg / "steps" / "ci.md").write_bytes(b"kind: auto\naway: run\n\n\xff\n")
    code, _, err = own(capsys, "explain")
    assert code == 2 and err.startswith("own-pr: ")


def test_closed_run_is_read_only(cfg, checkout, capsys):
    own(capsys, "start")
    rid = cli.open_journal().open_runs()[0]["id"]
    own(capsys, "close")
    for argv in (("--run", rid, "next"), ("--run", rid, "env", "claim", "rc09"), ("adopt", rid)):
        code, _, err = own(capsys, *argv)
        assert code == 2 and "closed" in err


def test_away_flow_reaches_handoff(cfg, checkout, capsys, monkeypatch):
    monkeypatch.setenv("OWN_PR_MODE", "away")
    own(capsys, "start")
    own(capsys, "step", "pr-draft", "done")
    own(capsys, "step", "decomment", "done")
    code, out, _ = own(capsys, "next")
    assert "NEXT: do review  (kind=human, mode=away, agent decides" in out
    own(capsys, "step", "review", "done", "--note", "took 2, declined 1")
    own(capsys, "step", "ci", "done")
    own(capsys, "step", "deploy-rc", "done")
    code, out, _ = own(capsys, "next")
    assert out.splitlines()[0] == "NEXT: do team-handoff  (kind=auto, mode=away)"
    assert own(capsys, "step", "team-handoff", "done")[0] == 0


def test_human_step_says_wait_for_igor(cfg, checkout, capsys):
    own(capsys, "start")
    own(capsys, "step", "pr-draft", "done")
    own(capsys, "step", "decomment", "done")
    code, out, _ = own(capsys, "next")
    assert out.splitlines()[0] == "NEXT: do eyeball  (kind=human, mode=attended, Igor's step — ask him and wait)"


def test_handoff_check_is_gone(cfg, checkout, capsys):
    own(capsys, "start")
    with pytest.raises(SystemExit):
        cli.main(["handoff-check"])

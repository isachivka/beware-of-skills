import json

import pytest

from conftest import REPO, git, repo_dir, write
from ownpr import cli


def next_line(out):
    return next(line for line in out.splitlines() if line.startswith("NEXT"))


def own(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err




def test_start_twice_fails(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    code, _, err = own(capsys, "start", "--profile", "full")
    assert code == 2 and "already exists" in err


def test_start_without_profile_lists_profiles(cfg, checkout, capsys, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "c1")
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
          "---\nroot: %s\nprofile.%s: quick\n---\n" % (checkout, REPO))
    code, out, _ = own(capsys, "start")
    assert "profile quick (origin)" in out and "origin wso" in out


def test_start_bad_mode_env(cfg, checkout, capsys, monkeypatch):
    monkeypatch.setenv("OWN_PR_MODE", "sleepy")
    code, _, err = own(capsys, "start", "--profile", "full")
    assert code == 2 and "OWN_PR_MODE" in err


def test_next_prints_step_prose_and_context(cfg, checkout, capsys):
    write(cfg / "origins" / "wso.md", "---\nroot: %s\n---\nStart every Slack post with 🤖 WS.\n" % checkout)
    own(capsys, "start", "--profile", "full")
    own(capsys, "bind", "https://github.com/pdffiller/jsfiller/pull/13300")
    code, out, _ = own(capsys, "next")
    assert code == 0
    assert next_line(out) == "NEXT: do pr-draft  (kind=auto, mode=attended)"
    assert "PR: https://github.com/pdffiller/jsfiller/pull/13300" in out
    assert "Origin wso: Start every Slack post with 🤖 WS." in out
    assert out.rstrip().endswith("Do pr-draft.")






def test_next_shows_existing_evidence(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    own(capsys, "step", "pr-draft", "running", "--evidence", "https://x/1")
    code, out, _ = own(capsys, "next")
    assert "NEXT: reconcile pr-draft" in out
    assert "Evidence so far: https://x/1" in out


def test_bind_rejects_other_repo(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    code, _, err = own(capsys, "bind", "https://github.com/pdffiller/pdffiller/pull/5")
    assert code == 2 and "belongs to github.com/pdffiller/pdffiller" in err


def test_unwritable_state_is_an_error_not_a_traceback(cfg, checkout, capsys, monkeypatch, tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    monkeypatch.setenv("OWN_PR_STATE_DIR", str(blocker / "state"))
    code, _, err = own(capsys, "start", "--profile", "full")
    assert code == 2 and err.startswith("own-pr: ")


def test_owe_and_clear(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    own(capsys, "owe", "look at the retry logic")
    owed = cli.open_journal().open_owed()[0]
    assert own(capsys, "clear", str(owed["id"]), "--by-human")[0] == 0
    assert cli.open_journal().open_owed() == []




def test_machine_away_reports_pinned_runs(cfg, checkout, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("OWN_PR_MODE", "attended")
    own(capsys, "start", "--profile", "full")
    code, out, _ = own(capsys, "away")
    assert code == 0
    assert open(str(tmp_path / "state" / "mode")).read().strip() == "away"
    assert "stays attended (terminal OWN_PR_MODE)" in out


def test_run_mode_override(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    own(capsys, "mode", "away")
    assert cli.open_journal().open_runs()[0]["mode_run"] == "away"
    own(capsys, "mode", "clear")
    assert cli.open_journal().open_runs()[0]["mode_run"] is None


def test_env_claim_between_runs(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    assert own(capsys, "env", "claim", "rc09")[0] == 0
    git(checkout, "checkout", "-q", "-b", "feature/other")
    own(capsys, "start", "--profile", "full")
    code, _, err = own(capsys, "env", "claim", "rc09")
    assert code == 2 and "rc09 is claimed by run" in err


def test_close_refuses_running(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    own(capsys, "step", "ci", "running")
    code, _, err = own(capsys, "close")
    assert code == 2 and "ci is running" in err
    own(capsys, "step", "ci", "done")
    assert own(capsys, "close")[0] == 0
    code, _, err = own(capsys, "next")
    assert code == 2 and "no open run" in err


def test_profile_switch(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    code, out, _ = own(capsys, "profile", "quick", "--by-human")
    assert code == 0 and "removed: decomment, deploy-rc" in out


def test_explain(cfg, checkout, capsys):
    write(repo_dir(cfg) / "profiles" / "bad.md", "---\ndescription: d\nsteps: pr-draft, nope\n---\n")
    own(capsys, "start", "--profile", "full")
    code, out, _ = own(capsys, "explain")
    assert code == 0
    assert "repo: github.com/pdffiller/jsfiller" in out
    assert "profile: full (explicit)" in out
    assert "mode: attended (default)" in out
    assert "requires" not in out
    assert "eyeball  kind=human away=defer" in out
    assert "invalid profile bad: unknown step 'nope'" in out


def test_explain_without_run(cfg, checkout, capsys):
    code, out, _ = own(capsys, "explain")
    assert code == 0 and "profiles: full, quick" in out


def test_adopt(cfg, checkout, capsys, monkeypatch):
    own(capsys, "start", "--profile", "full")
    rid = cli.open_journal().open_runs()[0]["id"]
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "c2")
    assert own(capsys, "adopt", rid)[0] == 0
    assert cli.open_journal().run(rid)["claude_session"] == "c2"


def test_export(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    code, out, _ = own(capsys, "export")
    assert json.loads(out)["runs"][0]["profile"] == "full"


def test_no_config_for_repo(cfg, checkout, capsys):
    git(checkout, "remote", "set-url", "origin", "git@github.com:someone/else.git")
    code, _, err = own(capsys, "start", "--profile", "full")
    assert code == 2 and err.startswith("own-pr: no own-pr config for github.com/someone/else")


def test_clear_needs_by_human(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    own(capsys, "owe", "look at it")
    owed = cli.open_journal().open_owed()[0]["id"]
    code, _, err = own(capsys, "clear", str(owed))
    assert code == 2 and "only the human" in err
    assert cli.open_journal().open_owed()[0]["id"] == owed


def test_non_utf8_config_is_an_error_not_a_traceback(cfg, checkout, capsys):
    (cfg / "steps" / "ci.md").write_bytes(b"---\nkind: auto\naway: run\n---\n\xff\n")
    code, _, err = own(capsys, "explain")
    assert code == 2 and err.startswith("own-pr: ")


def test_closed_run_is_read_only(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    rid = cli.open_journal().open_runs()[0]["id"]
    own(capsys, "close")
    for argv in (("--run", rid, "next"), ("--run", rid, "env", "claim", "rc09"), ("adopt", rid)):
        code, _, err = own(capsys, *argv)
        assert code == 2 and "closed" in err


def test_away_flow_reaches_handoff(cfg, checkout, capsys, monkeypatch):
    monkeypatch.setenv("OWN_PR_MODE", "away")
    own(capsys, "start", "--profile", "full")
    own(capsys, "step", "pr-draft", "done")
    own(capsys, "step", "decomment", "done")
    code, out, _ = own(capsys, "next")
    assert "NEXT: do review  (kind=human, mode=away, agent decides" in out
    own(capsys, "step", "review", "done", "--note", "took 2, declined 1")
    own(capsys, "step", "ci", "done")
    own(capsys, "step", "deploy-rc", "done")
    code, out, _ = own(capsys, "next")
    assert next_line(out) == "NEXT: do team-handoff  (kind=auto, mode=away)"
    assert own(capsys, "step", "team-handoff", "done")[0] == 0


def test_human_step_says_wait(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    own(capsys, "step", "pr-draft", "done")
    own(capsys, "step", "decomment", "done")
    code, out, _ = own(capsys, "next")
    assert next_line(out) == "NEXT: do eyeball  (kind=human, mode=attended, the human's step — ask them and wait)"


def test_handoff_check_is_gone(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    with pytest.raises(SystemExit):
        cli.main(["handoff-check"])


def test_bind_normalises_the_url(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    own(capsys, "bind", "https://github.com/pdffiller/jsfiller/pull/7/")
    assert cli.open_journal().open_runs()[0]["pr_url"] == "https://github.com/pdffiller/jsfiller/pull/7"


def test_explain_shows_what_it_can_when_the_profile_breaks(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    write(repo_dir(cfg) / "profiles" / "full.md", "---\ndescription: d\nsteps: pr-draft, nope\n---\n")
    code, out, err = own(capsys, "explain")
    assert code == 2
    assert "repo: github.com/pdffiller/jsfiller" in out and "invalid profile full" in out
    assert "not usable" in err


COMMANDS = ("start", "bind", "next", "step", "owe", "clear", "profile", "mode", "away", "attended",
            "explain", "env", "adopt", "close", "export")


def test_help_documents_every_command(capsys):
    import re
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    for cmd in COMMANDS:
        assert re.search(r"^\s+%s\s+\S" % cmd, out, re.M), cmd
    assert "own-pr start" in out and "own-pr next" in out and "prs" in out


@pytest.mark.parametrize("cmd", COMMANDS)
def test_each_command_has_a_description(cmd, capsys):
    with pytest.raises(SystemExit):
        cli.main([cmd, "--help"])
    usage, _, rest = capsys.readouterr().out.partition("\n\n")
    assert rest.strip() and not rest.lstrip().startswith(("positional", "options")), cmd


def test_step_help_explains_statuses(capsys):
    with pytest.raises(SystemExit):
        cli.main(["step", "--help"])
    out = capsys.readouterr().out
    for word in ("pending", "running", "done", "failed", "skipped", "--by-human", "--evidence", "--note"):
        assert word in out
    assert "deferred" not in out


def test_prs_help(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"], prog="prs")
    out = capsys.readouterr().out
    for word in ("owed", "go", "--no-gh", "owner/repo#N"):
        assert word in out


def test_debt_outlives_close(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    rid = cli.open_journal().open_runs()[0]["id"]
    own(capsys, "owe", "look at the agent's picks")
    own(capsys, "close")
    assert cli.main(["owed"], prog="prs") == 0
    out = capsys.readouterr().out
    assert "look at the agent's picks" in out and "closed" in out
    owed = cli.open_journal().open_owed()[0]["id"]
    assert own(capsys, "--run", rid, "clear", str(owed), "--by-human")[0] == 0
    assert cli.open_journal().open_owed() == []
    code, _, err = own(capsys, "--run", rid, "next")
    assert code == 2 and "closed" in err


def test_watch_needs_a_bound_pr(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    code, _, err = own(capsys, "watch")
    assert code == 2 and "bind" in err


def test_watch_notify_needs_an_agterm_session(cfg, checkout, capsys):
    own(capsys, "start", "--profile", "full")
    own(capsys, "bind", "https://github.com/pdffiller/jsfiller/pull/7")
    code, _, err = own(capsys, "watch", "--notify")
    assert code == 2 and "agterm" in err


def test_start_records_the_pane(cfg, checkout, capsys, monkeypatch):
    monkeypatch.setenv("AGTERM_SESSION_ID", "A1")
    monkeypatch.setenv("AGTERM_PANE", "right")
    own(capsys, "start", "--profile", "full")
    assert cli.open_journal().open_runs()[0]["agterm_pane"] == "right"


def bound_run(capsys, monkeypatch):
    from ownpr import overview

    def no_polling(*a):
        raise AssertionError("watch must not poll GitHub in this test")
    monkeypatch.setattr(overview, "watch", no_polling)
    monkeypatch.setenv("AGTERM_SESSION_ID", "A1")
    own(capsys, "start", "--profile", "full")
    own(capsys, "bind", "https://github.com/pdffiller/jsfiller/pull/7")
    return cli.open_journal().open_runs()[0]["id"]


def test_watch_refuses_a_second_watcher(cfg, checkout, capsys, monkeypatch, tmp_path):
    import os
    rid = bound_run(capsys, monkeypatch)
    pidfile = tmp_path / "state" / ("watch-%s.pid" % rid)
    pidfile.write_text(str(os.getppid()))
    code, _, err = own(capsys, "watch", "--notify")
    assert code == 2 and "already watching" in err


def test_watch_takes_over_a_stale_pidfile_and_cleans_up(cfg, checkout, capsys, monkeypatch, tmp_path):
    from ownpr import overview
    rid = bound_run(capsys, monkeypatch)
    pidfile = tmp_path / "state" / ("watch-%s.pid" % rid)
    pidfile.write_text("999999")
    typed = []
    monkeypatch.setattr(overview, "watch", lambda *a: "reviews 0 -> 1")
    monkeypatch.setattr(overview, "real_type", lambda *a: typed.append(a) or True)
    code, out, _ = own(capsys, "watch", "--notify")
    assert code == 0 and "reviews 0 -> 1" in out and typed
    assert not pidfile.exists()


def test_watch_detach_spawns_itself_in_a_new_session(cfg, checkout, capsys, monkeypatch):
    import subprocess
    bound_run(capsys, monkeypatch)
    spawned, real_popen = [], subprocess.Popen

    class P:
        pid = 4242

        def __new__(cls, args, **kw):
            if "watch" not in args:
                return real_popen(args, **kw)
            spawned.append((args, kw))
            return super().__new__(cls)

        def __init__(self, args, **kw):
            pass
    monkeypatch.setattr(subprocess, "Popen", P)
    code, out, _ = own(capsys, "watch", "--notify", "--detach")
    args, kw = spawned[0]
    assert code == 0 and "4242" in out
    assert "--notify" in args and "--detach" not in args and kw["start_new_session"] is True


def test_detach_needs_notify(cfg, checkout, capsys, monkeypatch):
    bound_run(capsys, monkeypatch)
    code, _, err = own(capsys, "watch", "--detach")
    assert code == 2 and "--notify" in err


def test_start_and_next_print_the_plan(cfg, checkout, capsys):
    code, out, _ = own(capsys, "start", "--profile", "full")
    assert "PLAN full: ▶pr-draft · decomment · eyeball[you]" in out
    code, out, _ = own(capsys, "next")
    assert out.splitlines()[0].startswith("PLAN full: ▶pr-draft")
    assert next_line(out).startswith("NEXT: do pr-draft")


def prs(capsys, *argv):
    code = cli.main(list(argv), prog="prs")
    out = capsys.readouterr()
    return code, out.out, out.err


def started_pr(capsys, monkeypatch, nudges):
    from ownpr import overview
    monkeypatch.setattr(overview, "real_type", lambda *a: nudges.append(a) or True)
    monkeypatch.setenv("AGTERM_SESSION_ID", "A1")
    own(capsys, "start", "--profile", "full")
    own(capsys, "bind", "https://github.com/pdffiller/jsfiller/pull/7")
    return cli.open_journal().open_runs()[0]["id"]


def test_prs_done_records_a_human_step_ahead_of_time(cfg, checkout, capsys, monkeypatch):
    nudges = []
    rid = started_pr(capsys, monkeypatch, nudges)
    code, out, _ = prs(capsys, "done", "7", "eyeball")
    assert code == 0
    st = cli.open_journal().steps(rid)["eyeball"]
    assert (st["status"], st["by"]) == ("done", "human")
    assert nudges == []


def test_prs_done_nudges_a_session_waiting_on_that_step(cfg, checkout, capsys, monkeypatch):
    nudges = []
    started_pr(capsys, monkeypatch, nudges)
    own(capsys, "step", "pr-draft", "done")
    own(capsys, "step", "decomment", "done")
    prs(capsys, "done", "7", "eyeball")
    session, pane, text = nudges[0]
    assert session == "A1" and "eyeball recorded by the human" in text and text.endswith("\n")


def test_prs_skip_needs_a_note(cfg, checkout, capsys, monkeypatch):
    started_pr(capsys, monkeypatch, [])
    code, _, err = prs(capsys, "skip", "7", "deploy-rc")
    assert code == 2 and "reason" in err
    assert prs(capsys, "skip", "7", "deploy-rc", "--note", "no rc")[0] == 0


def test_prs_away_switches_one_run(cfg, checkout, capsys, monkeypatch):
    nudges = []
    rid = started_pr(capsys, monkeypatch, nudges)
    own(capsys, "step", "pr-draft", "done")
    own(capsys, "step", "decomment", "done")
    assert prs(capsys, "away", "7")[0] == 0
    assert cli.open_journal().run(rid)["mode_run"] == "away"
    assert nudges and "now away" in nudges[0][2]
    assert prs(capsys, "attended", "7")[0] == 0
    assert cli.open_journal().run(rid)["mode_run"] == "attended"


def test_prs_done_unknown_step(cfg, checkout, capsys, monkeypatch):
    started_pr(capsys, monkeypatch, [])
    code, _, err = prs(capsys, "done", "7", "nope")
    assert code == 2 and "not in profile" in err

import pytest

from conftest import REPO, repo_dir, write
from ownpr import config, engine
from ownpr.journal import Journal


@pytest.fixture
def env(cfg, tmp_path):
    j = Journal(str(tmp_path / "state" / "own-pr.db"))
    repo = config.load_repo(REPO)
    rid = j.create_run(REPO, "feature/x", "/co", "full", "explicit", repo.profiles["full"].steps)
    return j, repo, rid


def run(j, rid):
    return j.run(rid)


def finish(j, rid, *steps):
    for s in steps:
        j.set_step(rid, s, "done", by="human")


def test_effective_mode():
    machine = ("attended", "default")
    assert engine.effective_mode({"mode_run": None, "mode_env": None}, machine) == machine
    assert engine.effective_mode({"mode_run": None, "mode_env": "away"}, machine)[0] == "away"
    assert engine.effective_mode({"mode_run": "attended", "mode_env": "away"}, ("away", "f"))[0] == "attended"


def test_next_walks_in_order(env):
    j, repo, rid = env
    a = engine.next_action(j, repo, run(j, rid), "attended")
    assert (a.kind, a.step) == ("do", "pr-draft")
    finish(j, rid, "pr-draft", "decomment")
    assert engine.next_action(j, repo, run(j, rid), "attended").step == "eyeball"


def test_running_step_is_reconciled_first(env):
    j, repo, rid = env
    j.set_step(rid, "ci", "running")
    a = engine.next_action(j, repo, run(j, rid), "attended")
    assert (a.kind, a.step) == ("reconcile", "ci")


def test_failed_step_is_retried(env):
    j, repo, rid = env
    finish(j, rid, "pr-draft")
    j.set_step(rid, "decomment", "failed")
    assert engine.next_action(j, repo, run(j, rid), "attended").kind == "retry"


def test_away_defers_eyeball_and_owes_it(env):
    j, repo, rid = env
    finish(j, rid, "pr-draft", "decomment")
    a = engine.next_action(j, repo, run(j, rid), "away")
    assert (a.kind, a.step, a.auto_pick) == ("do", "review", True)
    assert j.steps(rid)["eyeball"]["status"] == "deferred"
    assert [o["step"] for o in j.open_owed(rid)] == ["eyeball"]


def test_attended_returns_to_deferred_step(env):
    j, repo, rid = env
    finish(j, rid, "pr-draft", "decomment")
    engine.next_action(j, repo, run(j, rid), "away")
    a = engine.next_action(j, repo, run(j, rid), "attended")
    assert (a.kind, a.step) == ("do", "eyeball")




def test_skip_rules(env):
    j, repo, rid = env
    r = run(j, rid)
    with pytest.raises(engine.RuleError, match="only the human"):
        engine.record_step(j, repo, r, "deploy-rc", "skipped", "attended")
    with pytest.raises(engine.RuleError, match="the human's reason"):
        engine.record_step(j, repo, r, "deploy-rc", "skipped", "attended", by_human=True)
    engine.record_step(j, repo, r, "deploy-rc", "skipped", "attended", note="no rc", by_human=True)
    assert j.steps(rid)["deploy-rc"]["by"] == "human"


def test_human_step_needs_the_human(env):
    j, repo, rid = env
    r = run(j, rid)
    with pytest.raises(engine.RuleError, match="the human's step"):
        engine.record_step(j, repo, r, "eyeball", "done", "attended")
    with pytest.raises(engine.RuleError, match="the human's step"):
        engine.record_step(j, repo, r, "review", "done", "attended", note="picked")
    engine.record_step(j, repo, r, "eyeball", "done", "attended", by_human=True)
    assert j.steps(rid)["eyeball"]["status"] == "done"


def test_auto_pick_in_away_owes_the_decision(env):
    j, repo, rid = env
    r = run(j, rid)
    with pytest.raises(engine.RuleError, match="--note"):
        engine.record_step(j, repo, r, "review", "done", "away")
    engine.record_step(j, repo, r, "review", "done", "away", note="took 3, declined 2")
    assert j.open_owed(rid)[0]["text"] == "review decided by the agent: took 3, declined 2"


def test_human_done_clears_owed_for_step(env):
    j, repo, rid = env
    j.add_owed(rid, "eyeball deferred", step="eyeball")
    engine.record_step(j, repo, run(j, rid), "eyeball", "done", "attended", by_human=True)
    assert j.open_owed(rid) == []


def test_clearing_deferred_item_completes_the_step(env):
    j, repo, rid = env
    finish(j, rid, "pr-draft", "decomment")
    engine.next_action(j, repo, run(j, rid), "away")
    owed = j.open_owed(rid)[0]["id"]
    engine.clear_owed(j, run(j, rid), owed, by_human=True)
    eyeball = j.steps(rid)["eyeball"]
    assert (eyeball["status"], eyeball["by"]) == ("done", "human")


def test_deferred_is_not_recorded_by_hand(env):
    j, repo, rid = env
    with pytest.raises(engine.RuleError, match="deferral"):
        engine.record_step(j, repo, run(j, rid), "eyeball", "deferred", "away")


def test_step_outside_profile(env):
    j, repo, rid = env
    with pytest.raises(engine.RuleError, match="not in profile full"):
        engine.record_step(j, repo, run(j, rid), "aqa", "done", "attended")




def test_switch_profile(env):
    j, repo, rid = env
    j.set_step(rid, "ci", "running")
    with pytest.raises(engine.RuleError, match="ci is running"):
        engine.switch_profile(j, repo, run(j, rid), "quick", by_human=True)
    j.set_step(rid, "ci", "done")
    added, removed = engine.switch_profile(j, repo, run(j, rid), "quick", by_human=False)
    assert (added, removed) == ([], ["decomment", "deploy-rc"])
    assert run(j, rid)["profile"] == "quick"
    assert "dropping decomment, deploy-rc" in j.open_owed(rid)[0]["text"]


def test_switch_to_invalid_profile(env):
    j, repo, rid = env
    with pytest.raises(engine.RuleError, match="no valid profile 'nope'"):
        engine.switch_profile(j, repo, run(j, rid), "nope", by_human=True)


def test_new_step_in_profile_is_picked_up(env, cfg):
    j, repo, rid = env
    finish(j, rid, "pr-draft", "decomment", "eyeball")
    write(cfg / "steps" / "strip-tests.md", "---\nkind: auto\naway: run\n---\nStrip.\n")
    write(repo_dir(cfg) / "profiles" / "full.md",
          "---\ndescription: d\nsteps: pr-draft, strip-tests, decomment, eyeball, review, ci,"
          " deploy-rc, team-handoff, team-feedback\n---\n")
    repo = config.load_repo(REPO)
    assert engine.next_action(j, repo, run(j, rid), "attended").step == "strip-tests"




def test_broken_profile_is_a_rule_error(env, cfg):
    j, repo, rid = env
    write(repo_dir(cfg) / "profiles" / "full.md", "---\ndescription: d\nsteps: pr-draft, pr-draft\n---\n")
    repo = config.load_repo(REPO)
    with pytest.raises(engine.RuleError, match="duplicate step 'pr-draft'"):
        engine.next_action(j, repo, run(j, rid), "attended")


def test_close_waits_for_running(env):
    j, repo, rid = env
    j.set_step(rid, "deploy-rc", "running")
    with pytest.raises(engine.RuleError, match="deploy-rc is running"):
        engine.close(j, run(j, rid))
    j.set_step(rid, "deploy-rc", "done")
    engine.close(j, run(j, rid))
    assert j.run(rid)["state"] == "closed"










def test_running_step_removed_from_profile_is_still_reconciled(env, cfg):
    j, repo, rid = env
    j.set_step(rid, "deploy-rc", "running")
    write(repo_dir(cfg) / "profiles" / "full.md",
          "---\ndescription: d\nsteps: pr-draft, decomment, eyeball, review, ci, team-handoff, team-feedback\n---\n")
    repo = config.load_repo(REPO)
    a = engine.next_action(j, repo, run(j, rid), "attended")
    assert (a.kind, a.step) == ("reconcile", "deploy-rc")
    engine.record_step(j, repo, run(j, rid), "deploy-rc", "done", "attended")
    assert j.steps(rid)["deploy-rc"]["status"] == "done"


def test_done_when_all_finished(env):
    j, repo, rid = env
    finish(j, rid, *repo.profiles["full"].steps)
    assert engine.next_action(j, repo, run(j, rid), "attended").kind == "done"


def test_pending_requeues_a_done_step(env):
    j, repo, rid = env
    finish(j, rid, "pr-draft", "decomment", "eyeball", "review")
    j.set_step(rid, "ci", "done", evidence="https://ci/old")
    engine.record_step(j, repo, run(j, rid), "ci", "pending", "attended")
    assert j.steps(rid)["ci"]["evidence"] is None
    a = engine.next_action(j, repo, run(j, rid), "attended")
    assert (a.kind, a.step) == ("do", "ci")


def test_peek_is_read_only(env):
    j, repo, rid = env
    finish(j, rid, "pr-draft", "decomment")
    a = engine.peek(j, repo, run(j, rid), "away")
    assert (a.kind, a.step, a.auto_pick) == ("do", "review", True)
    assert j.steps(rid)["eyeball"]["status"] == "pending"
    assert j.open_owed(rid) == []


@pytest.fixture
def with_merge(cfg, tmp_path):
    write(cfg / "steps" / "merge.md", "---\nkind: human\naway: wait\n---\nThe human merges.\n")
    write(repo_dir(cfg) / "profiles" / "full.md",
          "---\ndescription: d\nsteps: pr-draft, decomment, eyeball, review, ci, deploy-rc, team-handoff,"
          " team-feedback, merge\n---\n")
    j = Journal(str(tmp_path / "state" / "own-pr.db"))
    repo = config.load_repo(REPO)
    rid = j.create_run(REPO, "feature/x", "/co", "full", "explicit", repo.profiles["full"].steps)
    return j, repo, rid


def away_to_handoff(j, repo, rid):
    finish(j, rid, "pr-draft", "decomment")
    assert engine.next_action(j, repo, run(j, rid), "away").step == "review"
    engine.record_step(j, repo, run(j, rid), "review", "done", "away", note="took 1")
    finish(j, rid, "ci", "deploy-rc")


def test_away_runs_through_team_handoff_with_debt(with_merge):
    j, repo, rid = with_merge
    away_to_handoff(j, repo, rid)
    a = engine.next_action(j, repo, run(j, rid), "away")
    assert (a.kind, a.step, a.waits) == ("do", "team-handoff", False)
    engine.record_step(j, repo, run(j, rid), "team-handoff", "done", "away")
    assert [o["step"] for o in j.open_owed(rid)] == ["eyeball", "review"]


def test_wait_step_stops_away_mode(with_merge):
    j, repo, rid = with_merge
    away_to_handoff(j, repo, rid)
    finish(j, rid, "team-handoff", "team-feedback")
    a = engine.next_action(j, repo, run(j, rid), "away")
    assert (a.kind, a.step, a.waits) == ("do", "merge", True)
    with pytest.raises(engine.RuleError, match="the human's step"):
        engine.record_step(j, repo, run(j, rid), "merge", "done", "away", note="merged it")
    assert j.steps(rid)["merge"]["status"] == "pending"


def test_attended_hands_back_deferred_steps_after_handoff(with_merge):
    j, repo, rid = with_merge
    away_to_handoff(j, repo, rid)
    finish(j, rid, "team-handoff")
    a = engine.next_action(j, repo, run(j, rid), "attended")
    assert (a.kind, a.step, a.waits) == ("do", "eyeball", True)


def test_failed_step_before_handoff_is_retried_first(env):
    j, repo, rid = env
    finish(j, rid, "pr-draft", "decomment", "eyeball", "review", "deploy-rc")
    j.set_step(rid, "ci", "failed")
    assert (engine.next_action(j, repo, run(j, rid), "away").kind) == "retry"


def test_agent_decision_and_its_debt_are_one_write(env, monkeypatch):
    j, repo, rid = env

    def boom(*a, **k):
        raise RuntimeError("lock timeout")
    monkeypatch.setattr(j, "add_owed", boom)
    with pytest.raises(RuntimeError):
        engine.record_step(j, repo, run(j, rid), "review", "done", "away", note="took 1")
    assert j.steps(rid)["review"]["status"] == "pending"


def test_attended_offers_deferred_steps_during_a_long_wait(with_merge):
    j, repo, rid = with_merge
    away_to_handoff(j, repo, rid)
    finish(j, rid, "team-handoff")
    j.set_step(rid, "team-feedback", "running")
    a = engine.next_action(j, repo, run(j, rid), "attended")
    assert (a.kind, a.step, a.waits) == ("do", "eyeball", True)
    a = engine.next_action(j, repo, run(j, rid), "away")
    assert (a.kind, a.step) == ("reconcile", "team-feedback")


def test_plan_line(with_merge):
    j, repo, rid = with_merge
    finish(j, rid, "pr-draft")
    j.set_step(rid, "ci", "failed")
    line = engine.plan_line(j, repo, run(j, rid), engine.Action("do", "decomment"))
    assert line == ("PLAN full: ✓pr-draft · ▶decomment · eyeball[you] · review[you] · ✗ci · deploy-rc"
                    " · team-handoff · team-feedback · merge[you, wait]")


def test_plan_line_marks_deferred_and_skipped(with_merge):
    j, repo, rid = with_merge
    j.set_step(rid, "eyeball", "deferred")
    j.set_step(rid, "deploy-rc", "skipped", by="human")
    line = engine.plan_line(j, repo, run(j, rid), engine.Action("done"))
    assert "eyeball[you, deferred]" in line and "-deploy-rc" in line and "▶" not in line


def test_recording_a_step_added_to_the_profile_later(env, cfg):
    j, repo, rid = env
    write(cfg / "steps" / "strip-tests.md", "---\nkind: auto\naway: run\n---\nStrip.\n")
    write(repo_dir(cfg) / "profiles" / "full.md",
          "---\ndescription: d\nsteps: pr-draft, strip-tests, decomment, eyeball, review, ci,"
          " deploy-rc, team-handoff, team-feedback\n---\n")
    repo = config.load_repo(REPO)
    engine.record_step(j, repo, run(j, rid), "strip-tests", "done", "attended")
    assert j.steps(rid)["strip-tests"]["status"] == "done"

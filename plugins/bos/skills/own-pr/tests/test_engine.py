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
        j.set_step(rid, s, "done", by="igor")


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


def test_handoff_blocked_until_clean(env):
    j, repo, rid = env
    finish(j, rid, "pr-draft", "decomment", "eyeball", "review", "ci")
    assert engine.handoff_blockers(j, repo, run(j, rid)) == ["deploy-rc is pending"]
    finish(j, rid, "deploy-rc")
    owed = j.add_owed(rid, "review decided by the agent: x", step="review")
    a = engine.next_action(j, repo, run(j, rid), "attended")
    assert (a.kind, a.step) == ("blocked", "team-handoff")
    assert a.blockers == ["owed to Igor: review decided by the agent: x"]
    engine.clear_owed(j, run(j, rid), owed, by_igor=True)
    a = engine.next_action(j, repo, run(j, rid), "attended")
    assert (a.kind, a.step) == ("do", "team-handoff")


def test_skip_rules(env):
    j, repo, rid = env
    r = run(j, rid)
    with pytest.raises(engine.RuleError, match="only Igor"):
        engine.record_step(j, repo, r, "deploy-rc", "skipped", "attended")
    with pytest.raises(engine.RuleError, match="required"):
        engine.record_step(j, repo, r, "ci", "skipped", "attended", note="x", by_igor=True)
    with pytest.raises(engine.RuleError, match="Igor's reason"):
        engine.record_step(j, repo, r, "deploy-rc", "skipped", "attended", by_igor=True)
    engine.record_step(j, repo, r, "deploy-rc", "skipped", "attended", note="no rc", by_igor=True)
    assert j.steps(rid)["deploy-rc"]["by"] == "igor"


def test_human_step_needs_igor(env):
    j, repo, rid = env
    r = run(j, rid)
    with pytest.raises(engine.RuleError, match="Igor's step"):
        engine.record_step(j, repo, r, "eyeball", "done", "attended")
    with pytest.raises(engine.RuleError, match="Igor's step"):
        engine.record_step(j, repo, r, "review", "done", "attended", note="picked")
    engine.record_step(j, repo, r, "eyeball", "done", "attended", by_igor=True)
    assert j.steps(rid)["eyeball"]["status"] == "done"


def test_auto_pick_in_away_owes_the_decision(env):
    j, repo, rid = env
    r = run(j, rid)
    with pytest.raises(engine.RuleError, match="--note"):
        engine.record_step(j, repo, r, "review", "done", "away")
    engine.record_step(j, repo, r, "review", "done", "away", note="took 3, declined 2")
    assert j.open_owed(rid)[0]["text"] == "review decided by the agent: took 3, declined 2"


def test_igor_done_clears_owed_for_step(env):
    j, repo, rid = env
    j.add_owed(rid, "eyeball deferred", step="eyeball")
    engine.record_step(j, repo, run(j, rid), "eyeball", "done", "attended", by_igor=True)
    assert j.open_owed(rid) == []


def test_clearing_deferred_item_completes_the_step(env):
    j, repo, rid = env
    finish(j, rid, "pr-draft", "decomment")
    engine.next_action(j, repo, run(j, rid), "away")
    owed = j.open_owed(rid)[0]["id"]
    engine.clear_owed(j, run(j, rid), owed, by_igor=True)
    eyeball = j.steps(rid)["eyeball"]
    assert (eyeball["status"], eyeball["by"]) == ("done", "igor")


def test_deferred_is_not_recorded_by_hand(env):
    j, repo, rid = env
    with pytest.raises(engine.RuleError, match="deferral"):
        engine.record_step(j, repo, run(j, rid), "eyeball", "deferred", "away")


def test_step_outside_profile(env):
    j, repo, rid = env
    with pytest.raises(engine.RuleError, match="not in profile full"):
        engine.record_step(j, repo, run(j, rid), "aqa", "done", "attended")


def test_waive(env):
    j, repo, rid = env
    j.add_owed(rid, "eyeball deferred", step="eyeball")
    engine.waive(j, repo, run(j, rid), by_igor=True)
    eyeball = j.steps(rid)["eyeball"]
    assert (eyeball["status"], eyeball["by"], eyeball["note"]) == ("skipped", "igor", "waived by Igor")
    assert j.open_owed(rid) == []


def test_switch_profile(env):
    j, repo, rid = env
    j.set_step(rid, "ci", "running")
    with pytest.raises(engine.RuleError, match="ci is running"):
        engine.switch_profile(j, repo, run(j, rid), "quick", by_igor=True)
    j.set_step(rid, "ci", "done")
    added, removed = engine.switch_profile(j, repo, run(j, rid), "quick", by_igor=False)
    assert (added, removed) == ([], ["decomment", "deploy-rc"])
    assert run(j, rid)["profile"] == "quick"
    assert "dropping decomment, deploy-rc" in j.open_owed(rid)[0]["text"]


def test_switch_to_invalid_profile(env):
    j, repo, rid = env
    with pytest.raises(engine.RuleError, match="no valid profile 'nope'"):
        engine.switch_profile(j, repo, run(j, rid), "nope", by_igor=True)


def test_new_step_in_profile_is_picked_up(env, cfg):
    j, repo, rid = env
    finish(j, rid, "pr-draft", "decomment", "eyeball")
    write(cfg / "steps" / "strip-tests.md", "kind: auto\naway: run\n\nStrip.\n")
    write(repo_dir(cfg) / "profiles" / "full.md",
          "description: d\nsteps: pr-draft, strip-tests, decomment, eyeball, review, ci,"
          " deploy-rc, team-handoff, team-feedback\n")
    repo = config.load_repo(REPO)
    assert engine.next_action(j, repo, run(j, rid), "attended").step == "strip-tests"


def test_removed_step_keeps_its_debt(env, cfg):
    j, repo, rid = env
    j.add_owed(rid, "deploy-rc deferred", step="deploy-rc")
    write(repo_dir(cfg) / "profiles" / "full.md",
          "description: d\nsteps: pr-draft, eyeball, review, ci, team-handoff, team-feedback\n")
    repo = config.load_repo(REPO)
    finish(j, rid, "pr-draft", "eyeball", "review", "ci")
    assert "owed to Igor: deploy-rc deferred" in engine.handoff_blockers(j, repo, run(j, rid))


def test_broken_profile_is_a_rule_error(env, cfg):
    j, repo, rid = env
    write(repo_dir(cfg) / "repo.md", "requires: review, ci\ndefault: quick\n")
    write(repo_dir(cfg) / "profiles" / "full.md", "description: d\nsteps: pr-draft, pr-draft\n")
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


def test_handoff_needs_igor_on_eyeball_even_if_shadowed(env, cfg):
    j, repo, rid = env
    write(repo_dir(cfg) / "steps" / "eyeball.md", "kind: auto\naway: run\n\nLook.\n")
    repo = config.load_repo(REPO)
    finish(j, rid, "pr-draft", "decomment", "review", "ci", "deploy-rc")
    engine.record_step(j, repo, run(j, rid), "eyeball", "done", "attended")
    assert engine.handoff_blockers(j, repo, run(j, rid)) == [
        "Igor has not inspected the PR (eyeball) or waived it"]


def test_team_handoff_cannot_be_recorded_while_blocked(env):
    j, repo, rid = env
    with pytest.raises(engine.RuleError, match="team handoff is blocked"):
        engine.record_step(j, repo, run(j, rid), "team-handoff", "running", "attended")


def test_failed_handoff_is_blocked_not_retried(env):
    j, repo, rid = env
    finish(j, rid, "pr-draft", "decomment", "eyeball", "review", "ci", "deploy-rc")
    j.set_step(rid, "team-handoff", "failed")
    j.add_owed(rid, "x")
    assert engine.next_action(j, repo, run(j, rid), "attended").kind == "blocked"


def test_handoff_check_before_new_step_row_exists(env, cfg):
    j, repo, rid = env
    write(cfg / "steps" / "strip-tests.md", "kind: auto\naway: run\n\nStrip.\n")
    write(repo_dir(cfg) / "profiles" / "full.md",
          "description: d\nsteps: pr-draft, strip-tests, decomment, eyeball, review, ci,"
          " deploy-rc, team-handoff, team-feedback\n")
    repo = config.load_repo(REPO)
    assert "strip-tests is pending" in engine.handoff_blockers(j, repo, run(j, rid))


def test_running_step_removed_from_profile_is_still_reconciled(env, cfg):
    j, repo, rid = env
    j.set_step(rid, "deploy-rc", "running")
    write(repo_dir(cfg) / "profiles" / "full.md",
          "description: d\nsteps: pr-draft, decomment, eyeball, review, ci, team-handoff, team-feedback\n")
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

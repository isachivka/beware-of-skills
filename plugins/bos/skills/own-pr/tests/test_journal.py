import json

import pytest

from ownpr.journal import Journal, JournalError

STEPS = ["pr-draft", "eyeball", "ci"]


@pytest.fixture
def j(tmp_path):
    return Journal(str(tmp_path / "state" / "own-pr.db"))


def new_run(j, branch="feature/x", **kw):
    return j.create_run("github.com/o/r", branch, "/co", "full", "explicit", STEPS, **kw)


def test_create_and_find(j):
    rid = new_run(j, identity={"claude": "c1", "codex": None, "agterm": "A1"}, mode_env="away")
    run = j.run(rid)
    assert (run["profile"], run["state"], run["mode_env"]) == ("full", "open", "away")
    assert (run["claude_session"], run["codex_session"], run["agterm_session"]) == ("c1", None, "A1")
    assert j.find_open_run("github.com/o/r", "feature/x")["id"] == rid
    assert set(j.steps(rid)) == set(STEPS)
    assert all(s["status"] == "pending" for s in j.steps(rid).values())


def test_one_open_run_per_branch(j):
    new_run(j)
    with pytest.raises(JournalError, match="already"):
        new_run(j)


def test_unknown_run(j):
    with pytest.raises(JournalError, match="no run"):
        j.run("deadbeef")


def test_set_step(j):
    rid = new_run(j)
    j.set_step(rid, "ci", "running")
    j.set_step(rid, "ci", "failed", note="lint")
    j.set_step(rid, "ci", "running")
    j.set_step(rid, "ci", "done", evidence="https://ci/1")
    ci = j.steps(rid)["ci"]
    assert (ci["status"], ci["attempts"], ci["evidence"], ci["note"]) == ("done", 2, "https://ci/1", "lint")


def test_step_event_records_mode(j):
    rid = new_run(j)
    j.set_step(rid, "ci", "done", mode="away (terminal OWN_PR_MODE)")
    event = [e for e in j.export()["runs"][0]["events"] if e["kind"] == "step"][0]
    assert json.loads(event["data"])["mode"] == "away (terminal OWN_PR_MODE)"


def test_set_unknown_step_or_status(j):
    rid = new_run(j)
    with pytest.raises(JournalError, match="no step 'nope'"):
        j.set_step(rid, "nope", "done")
    with pytest.raises(JournalError, match="status"):
        j.set_step(rid, "ci", "finished")


def test_ensure_steps(j):
    rid = new_run(j)
    assert j.ensure_steps(rid, ["pr-draft", "aqa"]) == ["aqa"]
    assert j.steps(rid)["aqa"]["status"] == "pending"


def test_owed(j):
    rid = new_run(j)
    a = j.add_owed(rid, "eyeball deferred", step="eyeball")
    b = j.add_owed(rid, "profile chosen by agent")
    assert [o["id"] for o in j.open_owed(rid)] == [a, b]
    j.clear_owed_for_step(rid, "eyeball")
    assert [o["id"] for o in j.open_owed(rid)] == [b]
    j.clear_owed(b)
    assert j.open_owed(rid) == []
    assert j.owed(a)["cleared"] is not None


def test_claims(j, tmp_path):
    r1, r2 = new_run(j, "feature/a"), new_run(j, "feature/b")
    j.claim("rc09", r1)
    j.claim("rc09", r1)
    other = Journal(str(tmp_path / "state" / "own-pr.db"))
    with pytest.raises(JournalError, match="rc09 is claimed by run %s" % r1):
        other.claim("rc09", r2)
    with pytest.raises(JournalError, match="does not hold"):
        j.release("rc09", r2)
    j.release("rc09", r1)
    j.claim("rc09", r2)
    assert [c["run_id"] for c in j.claims()] == [r2]


def test_claim_of_closed_run_is_free(j):
    r1, r2 = new_run(j, "feature/a"), new_run(j, "feature/b")
    j.claim("rc09", r1)
    j.close_run(r1)
    assert j.run(r1)["state"] == "closed"
    j.claim("rc09", r2)
    assert j.find_open_run("github.com/o/r", "feature/a") is None


def test_update_run_rejects_unknown_field(j):
    rid = new_run(j)
    j.update_run(rid, pr_url="https://github.com/o/r/pull/7", pr_number=7)
    assert j.run(rid)["pr_number"] == 7
    with pytest.raises(JournalError, match="field"):
        j.update_run(rid, state="closed")


def test_export(j):
    rid = new_run(j)
    j.add_owed(rid, "x")
    data = j.export()
    run = data["runs"][0]
    assert run["id"] == rid
    assert set(run["steps"]) == set(STEPS)
    assert run["owed"][0]["text"] == "x"
    assert any(e["kind"] == "start" for e in run["events"])


def _add_owed_many(path, run_id, n):
    j = Journal(path)
    for i in range(n):
        j.add_owed(run_id, "item %d" % i)


def test_concurrent_writers(tmp_path):
    import multiprocessing
    path = str(tmp_path / "state" / "own-pr.db")
    rid = new_run(Journal(path))
    procs = [multiprocessing.Process(target=_add_owed_many, args=(path, rid, 25)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    assert [p.exitcode for p in procs] == [0, 0, 0, 0]
    assert len(Journal(path).open_owed(rid)) == 100


def test_nested_tx_rolls_back_together(j):
    rid = new_run(j)
    with pytest.raises(RuntimeError):
        with j.tx():
            j.set_step(rid, "ci", "done")
            raise RuntimeError("boom")
    assert j.steps(rid)["ci"]["status"] == "pending"


def test_old_journal_gains_new_columns(tmp_path):
    import sqlite3
    path = str(tmp_path / "old.db")
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, repo TEXT NOT NULL, branch TEXT NOT NULL,"
               " checkout TEXT NOT NULL, pr_url TEXT, pr_number INTEGER, origin TEXT, profile TEXT NOT NULL,"
               " profile_by TEXT NOT NULL, mode_env TEXT, mode_run TEXT, claude_session TEXT,"
               " codex_session TEXT, agterm_session TEXT, state TEXT NOT NULL DEFAULT 'open',"
               " created REAL NOT NULL, updated REAL NOT NULL)")
    db.commit()
    db.close()
    j = Journal(path)
    rid = j.create_run("github.com/o/r", "b", "/co", "full", "explicit", STEPS,
                       identity={"agterm": "A", "pane": "left"})
    assert j.run(rid)["agterm_pane"] == "left"


def test_loop_fields_and_closed_runs(j):
    rid = j.create_run("github.com/o/r", "develop", "/co", "loop", "explicit", STEPS, loop_id="L", iteration=3)
    run = j.run(rid)
    assert (run["loop_id"], run["iteration"]) == ("L", 3)
    j.close_run(rid)
    other = new_run(j, "feature/b")
    j.close_run(other)
    assert [r["id"] for r in j.closed_runs()] == [other, rid]


def test_open_run_found_by_its_pr_branch(j):
    rid = j.create_run("github.com/o/r", "develop", "/co", "loop", "explicit", STEPS)
    j.update_run(rid, pr_url="https://github.com/o/r/pull/9", pr_number=9, pr_branch="feature/wave57")
    assert j.find_open_run("github.com/o/r", "feature/wave57")["id"] == rid
    assert j.find_open_run("github.com/o/r", "develop")["id"] == rid
    assert j.find_open_run("github.com/o/r", "feature/other") is None

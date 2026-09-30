import pytest

from conftest import REPO
from ownpr import cli, config, engine, overview
from ownpr.journal import Journal

URL = "https://github.com/pdffiller/jsfiller/pull/13300"


@pytest.fixture
def j(cfg, tmp_path):
    return Journal(str(tmp_path / "state" / "own-pr.db"))


def start(j, branch, url=None, agterm="2F400916-AAAA"):
    steps = config.load_repo(REPO).profiles["full"].steps
    rid = j.create_run(REPO, branch, "/co", "full", "explicit", steps,
                       identity={"claude": None, "codex": None, "agterm": agterm})
    if url:
        j.update_run(rid, pr_url=url, pr_number=int(url.rsplit("/", 1)[1]))
    return rid


def fake_gh(pr_state="OPEN", rollup=None, open_prs=()):
    def gh(args):
        if args[:2] == ["pr", "view"]:
            return {"state": pr_state, "title": "fix(rte): stop the spacing bug", "isDraft": True,
                    "statusCheckRollup": rollup or []}
        if args[:2] == ["search", "prs"]:
            return list(open_prs)
        return None
    return gh


def test_ci_summary():
    assert overview.ci_summary([]) == "-"
    assert overview.ci_summary([{"status": "COMPLETED", "conclusion": "SUCCESS"},
                                {"status": "COMPLETED", "conclusion": "SKIPPED"}]) == "green"
    assert overview.ci_summary([{"status": "IN_PROGRESS", "conclusion": ""}]) == "pending"
    assert overview.ci_summary([{"state": "PENDING"}]) == "pending"
    assert overview.ci_summary([{"conclusion": "FAILURE"}, {"status": "IN_PROGRESS"}]) == "red"


def test_ago():
    assert overview.ago(1000, now=1000 + 120) == "2m"
    assert overview.ago(1000, now=1000 + 7200) == "2h"
    assert overview.ago(1000, now=1000 + 3 * 86400) == "3d"






def test_table(j):
    rid = start(j, "feature/x", URL)
    j.set_step(rid, "ci", "running")
    j.add_owed(rid, "eyeball deferred", step="eyeball")
    j.claim("rc09", rid)
    start(j, "feature/y", agterm=None)
    gh = fake_gh(rollup=[{"status": "COMPLETED", "conclusion": "SUCCESS"}],
                 open_prs=[{"url": URL, "title": "t", "repository": {"nameWithOwner": "pdffiller/jsfiller"}},
                           {"url": "https://github.com/pdffiller/jsfiller/pull/1", "title": "old one",
                            "repository": {"nameWithOwner": "pdffiller/jsfiller"}}])
    out = overview.table(j, gh)
    row = next(l for l in out.splitlines() if l.startswith("#13300"))
    for part in ("pdffiller/jsfiller", "fix(rte): stop the spacing", "full", "ci running",
                 "eyeball", "green", "2F400916"):
        assert part in row
    assert "rc09" not in row and "RC" not in out.splitlines()[0]
    other = next(l for l in out.splitlines() if "feature/y" in l)
    assert other.startswith("-")
    assert "Untracked open PRs:" in out
    assert "#1 pdffiller/jsfiller  old one" in out
    assert "#13300 pdffiller/jsfiller  t" not in out


def test_merged_run_stays_open_until_a_step_closes_it(j):
    rid = start(j, "feature/x", URL)
    out = overview.table(j, fake_gh(pr_state="MERGED"))
    assert j.run(rid)["state"] == "open"
    row = next(l for l in out.splitlines() if l.startswith("#13300"))
    assert "merged" in row


def test_merged_run_with_running_step_stays_open(j):
    rid = start(j, "feature/x", URL)
    j.set_step(rid, "deploy-rc", "running")
    out = overview.table(j, fake_gh(pr_state="MERGED"))
    assert j.run(rid)["state"] == "open"
    assert "merged" in out


def test_table_without_gh(j):
    start(j, "feature/x", URL)
    out = overview.table(j, lambda args: None)
    row = next(l for l in out.splitlines() if l.startswith("#13300"))
    assert "feature/x" in row
    assert "Untracked" not in out


def test_table_with_broken_profile(j, cfg):
    from conftest import repo_dir, write
    start(j, "feature/x", URL)
    write(repo_dir(cfg) / "profiles" / "full.md", "description: d\nsteps: nope\n")
    out = overview.table(j, lambda args: None)
    assert "config error" in out


def test_owed_report(j):
    rid = start(j, "feature/x", URL)
    oid = j.add_owed(rid, "review decided by the agent: took 3", step="review")
    out = overview.owed_report(j)
    assert "#13300 (feature/x, run %s)" % rid in out
    assert "  [%d] review decided by the agent: took 3" % oid in out


def test_owed_report_empty(j):
    assert overview.owed_report(j) == "Nothing is waiting on you."


def test_go(j):
    start(j, "feature/x", URL)
    picked = []
    assert "2F400916" in overview.go(j, "13300", lambda sid: picked.append(sid) or True)
    assert picked == ["2F400916-AAAA"]
    with pytest.raises(ValueError, match="no longer exists"):
        overview.go(j, "13300", lambda sid: False)
    with pytest.raises(ValueError, match="no open run for 999"):
        overview.go(j, "999", lambda sid: True)


def test_go_ambiguous_number(j):
    start(j, "feature/x", URL)
    other = j.create_run("github.com/pdffiller/pdffiller", "feature/z", "/co2", "full", "explicit",
                         ["pr-draft"], identity={"agterm": "B"})
    j.update_run(other, pr_url="https://github.com/pdffiller/pdffiller/pull/13300", pr_number=13300)
    with pytest.raises(ValueError, match="ambiguous"):
        overview.go(j, "13300", lambda sid: True)
    assert overview.go(j, "pdffiller/pdffiller#13300", lambda sid: True) == "switched to agterm session B"
    assert "2F400916" in overview.go(j, "https://github.com/pdffiller/jsfiller/pull/13300",
                                     lambda sid: True)


def test_go_without_recorded_session(j):
    start(j, "feature/x", URL, agterm=None)
    with pytest.raises(ValueError, match="no agterm session recorded"):
        overview.go(j, "13300", lambda sid: True)


def test_prs_entrypoint(j, capsys, monkeypatch):
    start(j, "feature/x", URL)
    monkeypatch.setattr(overview, "real_gh", lambda args: None)
    assert cli.main(["--no-gh"], prog="prs") == 0
    assert "#13300" in capsys.readouterr().out
    assert cli.main(["owed"], prog="prs") == 0
    assert cli.main(["go", "999"], prog="prs") == 2


def test_prs_unwritable_state(cfg, monkeypatch, tmp_path, capsys):
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    monkeypatch.setenv("OWN_PR_STATE_DIR", str(blocker / "state"))
    assert cli.main([], prog="prs") == 2
    assert capsys.readouterr().err.startswith("prs: ")




def test_label():
    assert overview.label(engine.Action("reconcile", "ci")) == "ci running"
    assert overview.label(engine.Action("retry", "ci")) == "ci failed"
    assert overview.label(engine.Action("do", "ci")) == "ci next"
    assert overview.label(engine.Action("do", "eyeball", waits=True)) == "eyeball waits for the human"
    assert overview.label(engine.Action("done")) == "done"


def test_now_reflects_mode(j):
    rid = start(j, "feature/x", URL)
    for s in ("pr-draft", "decomment", "review", "ci", "deploy-rc"):
        j.set_step(rid, s, "done", by="human")

    def row():
        return next(l for l in overview.table(j, lambda a: None).splitlines() if l.startswith("#13300"))
    j.update_run(rid, mode_run="away")
    assert "team-handoff next" in row()
    j.update_run(rid, mode_run="attended")
    assert "eyeball waits for the human" in row()

import os
import sys
import textwrap

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

REPO = "github.com/pdffiller/jsfiller"
STEPS = {
    "pr-draft": ("auto", "run"),
    "decomment": ("auto", "run"),
    "eyeball": ("human", "defer"),
    "review": ("human", "auto-pick"),
    "ci": ("auto", "run"),
    "deploy-rc": ("auto", "run"),
    "team-handoff": ("auto", "run"),
    "team-feedback": ("auto", "run"),
}
FULL = "pr-draft, decomment, eyeball, review, ci, deploy-rc, team-handoff, team-feedback"
QUICK = "pr-draft, eyeball, review, ci, team-handoff, team-feedback"


def write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as fh:
        fh.write(textwrap.dedent(text).lstrip())


def repo_dir(root):
    return root / "repos" / "github.com" / "pdffiller" / "jsfiller"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    root = tmp_path / "config"
    for sid, (kind, away) in STEPS.items():
        write(root / "steps" / (sid + ".md"),
              "---\nkind: %s\naway: %s\n---\nDo %s.\n" % (kind, away, sid))
    write(repo_dir(root) / "profiles" / "full.md",
          "---\ndescription: runtime change\nsteps: %s\n---\n" % FULL)
    write(repo_dir(root) / "profiles" / "quick.md",
          "---\ndescription: small fix\nsteps: %s\n---\n" % QUICK)
    monkeypatch.setenv("OWN_PR_CONFIG_DIR", str(root))
    monkeypatch.setenv("OWN_PR_STATE_DIR", str(tmp_path / "state"))
    for key in ("OWN_PR_MODE", "OWN_PR_ORIGIN", "CLAUDE_CODE_SESSION_ID",
                "CODEX_THREAD_ID", "AGTERM_SESSION_ID"):
        monkeypatch.delenv(key, raising=False)
    return root

import subprocess


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "-c", "commit.gpgsign=false", *args],
                   cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    repo = tmp_path / "jsfiller"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "develop")
    git(repo, "commit", "-q", "--allow-empty", "-m", "init")
    git(repo, "remote", "add", "origin", "git@github.com:pdffiller/jsfiller.git")
    git(repo, "checkout", "-q", "-b", "feature/x")
    monkeypatch.chdir(repo)
    return repo


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never reach GitHub or agterm; a test that needs an answer stubs it itself."""
    from ownpr import overview
    monkeypatch.setattr(overview, "real_gh", lambda args: None)
    monkeypatch.setattr(overview, "real_type", lambda *a: False)
    monkeypatch.setattr(overview, "real_select", lambda sid: False)

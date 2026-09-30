import os

import pytest

from conftest import git
from ownpr import config, context


@pytest.mark.parametrize("url", [
    "git@github.com:pdffiller/jsfiller.git",
    "https://github.com/pdffiller/jsfiller.git",
    "https://github.com/pdffiller/jsfiller",
    "ssh://git@github.com/pdffiller/jsfiller.git",
])
def test_repo_id_from_url(url):
    assert context.repo_id_from_url(url) == "github.com/pdffiller/jsfiller"


@pytest.mark.parametrize("url", ["/local/path/repo", "git@github.com:onlyowner.git"])
def test_repo_id_from_bad_url(url):
    with pytest.raises(context.ContextError):
        context.repo_id_from_url(url)


def test_checkout(checkout):
    co = context.checkout(str(checkout))
    assert co["repo"] == "github.com/pdffiller/jsfiller"
    assert co["branch"] == "feature/x"
    assert co["toplevel"] == os.path.realpath(str(checkout))
    assert co["main_root"] == os.path.realpath(str(checkout))


def test_checkout_from_linked_worktree(checkout, tmp_path):
    wt = tmp_path / "wt"
    git(checkout, "worktree", "add", "-q", "-b", "feature/y", str(wt))
    co = context.checkout(str(wt))
    assert co["branch"] == "feature/y"
    assert co["toplevel"] == os.path.realpath(str(wt))
    assert co["main_root"] == os.path.realpath(str(checkout))


def test_checkout_without_remote(checkout):
    git(checkout, "remote", "remove", "origin")
    with pytest.raises(context.ContextError, match="remote get-url origin"):
        context.checkout(str(checkout))


def test_checkout_outside_git(tmp_path):
    with pytest.raises(context.ContextError):
        context.checkout(str(tmp_path))


def test_identity():
    ident = context.identity({"CLAUDE_CODE_SESSION_ID": "c1", "AGTERM_SESSION_ID": "A1"})
    assert ident == {"claude": "c1", "codex": None, "agterm": "A1"}


def origins():
    return {"wso": config.Origin("wso", "/r/wso", "", {}, "x"),
            "jso": config.Origin("jso", "/r/jso", "", {}, "y")}


def test_resolve_origin_precedence():
    assert context.resolve_origin(origins(), "jso", "wso", "/r/wso").name == "jso"
    assert context.resolve_origin(origins(), None, "wso", "/r/jso").name == "wso"
    assert context.resolve_origin(origins(), None, None, "/r/jso").name == "jso"
    assert context.resolve_origin(origins(), None, None, "/elsewhere") is None


def test_resolve_unknown_origin():
    with pytest.raises(context.ContextError, match="unknown origin 'nope'"):
        context.resolve_origin(origins(), "nope", None, "/r/wso")

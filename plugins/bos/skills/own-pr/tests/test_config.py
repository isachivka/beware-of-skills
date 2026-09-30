import pytest

from conftest import REPO, repo_dir, write
from ownpr import config


def test_step_header_and_body(cfg):
    repo = config.load_repo(REPO)
    step = repo.steps["eyeball"]
    assert (step.kind, step.away) == ("human", "defer")
    assert step.body == "Do eyeball."
    assert step.source.endswith("steps/eyeball.md")


def test_inline_comment_stripped(cfg):
    write(cfg / "steps" / "ci.md", "kind: auto   # auto | human\naway: run\n\nWait.\n")
    assert config.load_repo(REPO).steps["ci"].kind == "auto"


def test_prose_line_inside_header_is_an_error(cfg):
    write(cfg / "steps" / "ci.md", "kind: auto\nWait for CI.\naway: run\n")
    with pytest.raises(config.ConfigError, match="not `key: value`"):
        config.load_repo(REPO)


def test_prose_after_blank_line_may_contain_colons(cfg):
    write(cfg / "steps" / "ci.md", "kind: auto\naway: run\n\nNote: wait for CI.\n")
    assert config.load_repo(REPO).steps["ci"].body == "Note: wait for CI."


def test_unknown_step_key(cfg):
    write(cfg / "steps" / "ci.md", "kind: auto\naway: run\nscope: head\n")
    with pytest.raises(config.ConfigError, match="unknown key 'scope'"):
        config.load_repo(REPO)


def test_bad_enum(cfg):
    write(cfg / "steps" / "ci.md", "kind: robot\naway: run\n")
    with pytest.raises(config.ConfigError, match="kind must be one of"):
        config.load_repo(REPO)


def test_duplicate_key(cfg):
    write(cfg / "steps" / "ci.md", "kind: auto\nkind: auto\naway: run\n")
    with pytest.raises(config.ConfigError, match="duplicate key"):
        config.load_repo(REPO)


def test_repo_step_shadows_global(cfg):
    write(repo_dir(cfg) / "steps" / "review.md",
          "kind: human\naway: auto-pick\n\nRun /crit-review.\n")
    step = config.load_repo(REPO).steps["review"]
    assert step.body == "Run /crit-review."
    assert "/repos/" in step.source


def test_profile_validation(cfg):
    pdir = repo_dir(cfg) / "profiles"
    write(pdir / "dup.md", "description: d\nsteps: pr-draft, eyeball, review, review, ci\n")
    write(pdir / "unknown.md", "description: d\nsteps: pr-draft, eyeball, review, ci, nope\n")
    write(pdir / "noreq.md", "description: d\nsteps: pr-draft, eyeball, ci\n")
    write(pdir / "noeye.md", "description: d\nsteps: pr-draft, review, ci, team-handoff\n")
    write(pdir / "empty.md", "description: d\nsteps:\n")
    write(pdir / "broken.md", "steps: pr-draft\n")
    repo = config.load_repo(REPO)
    assert set(repo.profiles) == {"full", "quick"}
    assert "duplicate step 'review'" in repo.invalid["dup"]
    assert "unknown step 'nope'" in repo.invalid["unknown"]
    assert "missing required step 'review'" in repo.invalid["noreq"]
    assert "team-handoff without eyeball before it" in repo.invalid["noeye"]
    assert "no steps" in repo.invalid["empty"]
    assert any("missing key 'description'" in e for e in repo.invalid["broken"])


def test_default_must_be_valid_profile(cfg):
    write(repo_dir(cfg) / "repo.md", "requires: review, ci\ndefault: nope\n")
    with pytest.raises(config.ConfigError, match="default profile 'nope'"):
        config.load_repo(REPO)


def test_default_auto(cfg):
    write(repo_dir(cfg) / "repo.md", "requires: review, ci\ndefault: auto\n")
    assert config.load_repo(REPO).default == "auto"


def test_required_step_must_exist(cfg):
    write(repo_dir(cfg) / "repo.md", "requires: review, nope\ndefault: auto\n")
    with pytest.raises(config.ConfigError, match="required step 'nope'"):
        config.load_repo(REPO)


def test_missing_repo_config(cfg):
    with pytest.raises(config.ConfigError, match="no own-pr config for github.com/a/b"):
        config.load_repo("github.com/a/b")


def test_origins(cfg, tmp_path):
    write(cfg / "origins" / "ws-observability.md",
          "root: %s\nstamp: 🤖 WS Agent\nprofile.%s: quick\n" % (tmp_path / "wso", REPO))
    origins = config.load_origins()
    o = origins["ws-observability"]
    assert o.stamp == "🤖 WS Agent"
    assert o.profiles == {REPO: "quick"}
    assert o.root.endswith("wso")


def test_origins_share_root(cfg, tmp_path):
    for name in ("a", "b"):
        write(cfg / "origins" / (name + ".md"), "root: %s\n" % (tmp_path / "same"))
    with pytest.raises(config.ConfigError, match="share root"):
        config.load_origins()


def test_origin_unknown_key(cfg, tmp_path):
    write(cfg / "origins" / "a.md", "root: %s\nsteps: x\n" % tmp_path)
    with pytest.raises(config.ConfigError, match="unknown key 'steps'"):
        config.load_origins()


def test_machine_mode_precedence(cfg, tmp_path):
    assert config.machine_mode() == ("attended", "default")
    write(cfg / "config.md", "mode: away\n")
    assert config.machine_mode()[0] == "away"
    flag = tmp_path / "state" / "mode"
    write(flag, "attended\n")
    assert config.machine_mode() == ("attended", str(flag))


def test_required_step_after_handoff(cfg):
    write(repo_dir(cfg) / "profiles" / "late.md",
          "description: d\nsteps: pr-draft, eyeball, team-handoff, review, ci\n")
    assert "required step 'review' after team-handoff" in config.load_repo(REPO).invalid["late"]

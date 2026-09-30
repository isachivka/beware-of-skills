import pytest

from conftest import REPO, repo_dir, write
from ownpr import config


def test_step_header_and_body(cfg):
    repo = config.load_repo(REPO)
    step = repo.steps["eyeball"]
    assert (step.kind, step.away) == ("human", "defer")
    assert step.body == "Do eyeball."
    assert step.source.endswith("steps/eyeball.md")


def test_values_are_literal_no_inline_comments(cfg):
    write(repo_dir(cfg) / "profiles" / "full.md",
          "description: fixes like PR #123 # and more\nsteps: pr-draft, eyeball, review, ci\n")
    assert config.load_repo(REPO).profiles["full"].description == "fixes like PR #123 # and more"


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
    write(pdir / "empty.md", "description: d\nsteps:\n")
    write(pdir / "broken.md", "steps: pr-draft\n")
    repo = config.load_repo(REPO)
    assert set(repo.profiles) == {"full", "quick"}
    assert "duplicate step 'review'" in repo.invalid["dup"]
    assert "unknown step 'nope'" in repo.invalid["unknown"]
    assert "missing required step 'review'" in repo.invalid["noreq"]
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
          "root: %s\nprofile.%s: quick\n\nStart every Slack post with 🤖 WS Agent.\n" % (tmp_path / "wso", REPO))
    origins = config.load_origins()
    o = origins["ws-observability"]
    assert o.notes == "Start every Slack post with 🤖 WS Agent."
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




def test_away_wait_is_a_valid_value(cfg):
    write(cfg / "steps" / "merge.md", "kind: human\naway: wait\n\nThe human merges.\n")
    assert config.load_repo(REPO).steps["merge"].away == "wait"


def test_handoff_without_eyeball_is_valid(cfg):
    write(repo_dir(cfg) / "profiles" / "bare.md", "description: d\nsteps: pr-draft, review, ci, team-handoff\n")
    assert "bare" in config.load_repo(REPO).profiles


def test_away_value_must_fit_kind(cfg):
    write(cfg / "steps" / "eyeball.md", "kind: human\naway: run\n")
    with pytest.raises(config.ConfigError, match="a human step takes away: defer|auto-pick|wait"):
        config.load_repo(REPO)


def test_origin_stamp_key_is_gone(cfg, tmp_path):
    write(cfg / "origins" / "a.md", "root: %s\nstamp: x\n" % tmp_path)
    with pytest.raises(config.ConfigError, match="unknown key 'stamp'"):
        config.load_origins()


def test_origin_without_root(cfg):
    write(cfg / "origins" / "typing-wave.md", "profile.%s: quick\n\nLogic must not change.\n" % REPO)
    o = config.load_origins()["typing-wave"]
    assert o.root is None and o.notes == "Logic must not change."

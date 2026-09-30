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
          "---\ndescription: fixes like PR #123 # and more\nsteps: pr-draft, eyeball, review, ci\n---\n")
    assert config.load_repo(REPO).profiles["full"].description == "fixes like PR #123 # and more"


def test_prose_line_inside_frontmatter_is_an_error(cfg):
    write(cfg / "steps" / "ci.md", "---\nkind: auto\nWait for CI.\naway: run\n---\n")
    with pytest.raises(config.ConfigError, match="not `key: value`"):
        config.load_repo(REPO)


def test_prose_after_blank_line_may_contain_colons(cfg):
    write(cfg / "steps" / "ci.md", "---\nkind: auto\naway: run\n---\nNote: wait for CI.\n")
    assert config.load_repo(REPO).steps["ci"].body == "Note: wait for CI."


def test_unknown_step_key(cfg):
    write(cfg / "steps" / "ci.md", "---\nkind: auto\naway: run\nscope: head\n---\n")
    with pytest.raises(config.ConfigError, match="unknown key 'scope'"):
        config.load_repo(REPO)


def test_bad_enum(cfg):
    write(cfg / "steps" / "ci.md", "---\nkind: robot\naway: run\n---\n")
    with pytest.raises(config.ConfigError, match="kind must be one of"):
        config.load_repo(REPO)


def test_duplicate_key(cfg):
    write(cfg / "steps" / "ci.md", "---\nkind: auto\nkind: auto\naway: run\n---\n")
    with pytest.raises(config.ConfigError, match="duplicate key"):
        config.load_repo(REPO)


def test_repo_step_shadows_global(cfg):
    write(repo_dir(cfg) / "steps" / "review.md",
          "---\nkind: human\naway: auto-pick\n---\nRun /crit-review.\n")
    step = config.load_repo(REPO).steps["review"]
    assert step.body == "Run /crit-review."
    assert "/repos/" in step.source


def test_profile_validation(cfg):
    pdir = repo_dir(cfg) / "profiles"
    write(pdir / "dup.md", "---\ndescription: d\nsteps: pr-draft, eyeball, review, review, ci\n---\n")
    write(pdir / "unknown.md", "---\ndescription: d\nsteps: pr-draft, eyeball, review, ci, nope\n---\n")
    write(pdir / "empty.md", "---\ndescription: d\nsteps:\n---\n")
    write(pdir / "broken.md", "---\nsteps: pr-draft\n---\n")
    repo = config.load_repo(REPO)
    assert set(repo.profiles) == {"full", "quick"}
    assert "duplicate step 'review'" in repo.invalid["dup"]
    assert "unknown step 'nope'" in repo.invalid["unknown"]
    assert "no steps" in repo.invalid["empty"]
    assert any("missing key 'description'" in e for e in repo.invalid["broken"])








def test_missing_repo_config(cfg):
    with pytest.raises(config.ConfigError, match="no own-pr config for github.com/a/b"):
        config.load_repo("github.com/a/b")


def test_origins(cfg, tmp_path):
    write(cfg / "origins" / "ws-observability.md",
          "---\nroot: %s\nprofile.%s: quick\n---\nStart every Slack post with 🤖 WS Agent.\n" % (tmp_path / "wso", REPO))
    origins = config.load_origins()
    o = origins["ws-observability"]
    assert o.notes == "Start every Slack post with 🤖 WS Agent."
    assert o.profiles == {REPO: "quick"}
    assert o.root.endswith("wso")


def test_origins_share_root(cfg, tmp_path):
    for name in ("a", "b"):
        write(cfg / "origins" / (name + ".md"), "---\nroot: %s\n---\n" % (tmp_path / "same"))
    with pytest.raises(config.ConfigError, match="share root"):
        config.load_origins()


def test_origin_unknown_key(cfg, tmp_path):
    write(cfg / "origins" / "a.md", "---\nroot: %s\nsteps: x\n---\n" % tmp_path)
    with pytest.raises(config.ConfigError, match="unknown key 'steps'"):
        config.load_origins()


def test_machine_mode_precedence(cfg, tmp_path):
    assert config.machine_mode() == ("attended", "default")
    write(cfg / "config.md", "---\nmode: away\n---\n")
    assert config.machine_mode()[0] == "away"
    flag = tmp_path / "state" / "mode"
    write(flag, "attended\n")
    assert config.machine_mode() == ("attended", str(flag))




def test_away_wait_is_a_valid_value(cfg):
    write(cfg / "steps" / "merge.md", "---\nkind: human\naway: wait\n---\nThe human merges.\n")
    assert config.load_repo(REPO).steps["merge"].away == "wait"


def test_handoff_without_eyeball_is_valid(cfg):
    write(repo_dir(cfg) / "profiles" / "bare.md", "---\ndescription: d\nsteps: pr-draft, review, ci, team-handoff\n---\n")
    assert "bare" in config.load_repo(REPO).profiles


def test_away_value_must_fit_kind(cfg):
    write(cfg / "steps" / "eyeball.md", "---\nkind: human\naway: run\n---\n")
    with pytest.raises(config.ConfigError, match="a human step takes away: defer|auto-pick|wait"):
        config.load_repo(REPO)


def test_origin_stamp_key_is_gone(cfg, tmp_path):
    write(cfg / "origins" / "a.md", "---\nroot: %s\nstamp: x\n---\n" % tmp_path)
    with pytest.raises(config.ConfigError, match="unknown key 'stamp'"):
        config.load_origins()


def test_origin_without_root(cfg):
    write(cfg / "origins" / "typing-wave.md", "---\nprofile.%s: quick\n---\nLogic must not change.\n" % REPO)
    o = config.load_origins()["typing-wave"]
    assert o.root is None and o.notes == "Logic must not change."


def test_frontmatter_must_close(cfg):
    write(cfg / "steps" / "ci.md", "---\nkind: auto\naway: run\n")
    with pytest.raises(config.ConfigError, match="frontmatter is not closed"):
        config.load_repo(REPO)


def test_file_without_frontmatter_has_no_keys(cfg):
    write(cfg / "steps" / "ci.md", "kind: auto\naway: run\n")
    with pytest.raises(config.ConfigError, match="missing key 'kind'"):
        config.load_repo(REPO)


def test_repo_is_just_a_directory(cfg):
    assert not (repo_dir(cfg) / "repo.md").exists()
    assert set(config.load_repo(REPO).profiles) == {"full", "quick"}

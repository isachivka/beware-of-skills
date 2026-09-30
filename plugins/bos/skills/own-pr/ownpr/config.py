"""Load and validate the own-pr process config: steps, profiles, repos, origins."""
import os
import re
from dataclasses import dataclass

KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_./-]*):[ \t]*(.*)$")
COMMENT_RE = re.compile(r"\s+#.*$")
STEP_KEYS = {"kind": ("auto", "human"), "away": ("run", "defer", "auto-pick", "wait")}
AWAY_BY_KIND = {"auto": ("run",), "human": ("defer", "auto-pick", "wait")}
MODES = ("attended", "away")


class ConfigError(Exception):
    pass


def config_dir():
    return os.environ.get("OWN_PR_CONFIG_DIR") or os.path.expanduser("~/.config/own-pr")


def state_dir():
    return os.environ.get("OWN_PR_STATE_DIR") or os.path.expanduser("~/.local/state/own-pr")


def read_md(path):
    """The header is every line up to the first blank one, each `key: value`; the rest is prose."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    keys, i = {}, 0
    while i < len(lines) and lines[i].strip():
        m = KEY_RE.match(lines[i])
        if not m:
            raise ConfigError("%s:%d: header line is not `key: value`: %r" % (path, i + 1, lines[i]))
        key = m.group(1)
        if key in keys:
            raise ConfigError("%s: duplicate key %r" % (path, key))
        keys[key] = COMMENT_RE.sub("", m.group(2)).strip()
        i += 1
    return keys, "\n".join(lines[i:]).strip()


def check_keys(keys, allowed, required, path):
    prefixes = tuple(a for a in allowed if a.endswith("."))
    for key in keys:
        if key not in allowed and not key.startswith(prefixes or ("\0",)):
            raise ConfigError("%s: unknown key %r" % (path, key))
    for key in required:
        if key not in keys:
            raise ConfigError("%s: missing key %r" % (path, key))


def split_list(value):
    return [x.strip() for x in value.split(",") if x.strip()]


@dataclass
class Step:
    id: str
    kind: str
    away: str
    body: str
    source: str


@dataclass
class Profile:
    name: str
    description: str
    steps: list
    source: str


@dataclass
class Repo:
    id: str
    requires: list
    default: str
    steps: dict
    profiles: dict
    invalid: dict
    source: str


@dataclass
class Origin:
    name: str
    root: str
    stamp: str
    profiles: dict
    source: str


def stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def md_files(directory):
    if not os.path.isdir(directory):
        return []
    return [os.path.join(directory, n) for n in sorted(os.listdir(directory)) if n.endswith(".md")]


def load_step(path):
    keys, body = read_md(path)
    check_keys(keys, STEP_KEYS, STEP_KEYS, path)
    for key, allowed in STEP_KEYS.items():
        if keys[key] not in allowed:
            raise ConfigError("%s: %s must be one of %s, got %r"
                              % (path, key, "|".join(allowed), keys[key]))
    if keys["away"] not in AWAY_BY_KIND[keys["kind"]]:
        raise ConfigError("%s: a %s step takes away: %s, got %r"
                          % (path, keys["kind"], "|".join(AWAY_BY_KIND[keys["kind"]]), keys["away"]))
    return Step(stem(path), keys["kind"], keys["away"], body, path)


def load_steps(directory):
    return {s.id: s for s in (load_step(p) for p in md_files(directory))}


def load_profile(path):
    keys, _ = read_md(path)
    check_keys(keys, ("description", "steps"), ("description", "steps"), path)
    return Profile(stem(path), keys["description"], split_list(keys["steps"]), path)


def profile_errors(profile, steps, requires):
    errors, seen = [], set()
    if not profile.description:
        errors.append("empty description")
    if not profile.steps:
        errors.append("no steps")
    for sid in profile.steps:
        if sid in seen:
            errors.append("duplicate step %r" % sid)
        seen.add(sid)
        if sid not in steps:
            errors.append("unknown step %r" % sid)
    for req in requires:
        if req not in seen:
            errors.append("missing required step %r" % req)
    return errors


def repo_dir(root, repo_id):
    return os.path.join(root, "repos", *repo_id.split("/"))


def load_repo(repo_id, root=None):
    root = root or config_dir()
    rdir = repo_dir(root, repo_id)
    path = os.path.join(rdir, "repo.md")
    if not os.path.isfile(path):
        raise ConfigError("no own-pr config for %s (expected %s)" % (repo_id, path))
    keys, _ = read_md(path)
    check_keys(keys, ("requires", "default"), ("default",), path)
    steps = load_steps(os.path.join(root, "steps"))
    steps.update(load_steps(os.path.join(rdir, "steps")))
    requires = split_list(keys.get("requires", ""))
    for req in requires:
        if req not in steps:
            raise ConfigError("%s: required step %r does not exist" % (path, req))
    profiles, invalid = {}, {}
    for ppath in md_files(os.path.join(rdir, "profiles")):
        try:
            profile = load_profile(ppath)
        except ConfigError as exc:
            invalid[stem(ppath)] = [str(exc)]
            continue
        errors = profile_errors(profile, steps, requires)
        if errors:
            invalid[profile.name] = errors
        else:
            profiles[profile.name] = profile
    default = keys["default"]
    if default != "auto" and default not in profiles:
        raise ConfigError("%s: default profile %r is not a valid profile" % (path, default))
    return Repo(repo_id, requires, default, steps, profiles, invalid, path)


def load_origins(root=None):
    root = root or config_dir()
    origins, roots = {}, {}
    for path in md_files(os.path.join(root, "origins")):
        keys, _ = read_md(path)
        check_keys(keys, ("root", "stamp", "profile."), ("root",), path)
        name = stem(path)
        oroot = os.path.realpath(os.path.expanduser(keys["root"]))
        if oroot in roots:
            raise ConfigError("origins %r and %r share root %s" % (roots[oroot], name, oroot))
        roots[oroot] = name
        profiles = {k[len("profile."):]: v for k, v in keys.items() if k.startswith("profile.")}
        origins[name] = Origin(name, oroot, keys.get("stamp", ""), profiles, path)
    return origins


def machine_mode(root=None, state=None):
    flag = os.path.join(state or state_dir(), "mode")
    if os.path.isfile(flag):
        with open(flag) as fh:
            mode = fh.read().strip()
        if mode not in MODES:
            raise ConfigError("%s: mode must be attended or away, got %r" % (flag, mode))
        return mode, flag
    path = os.path.join(root or config_dir(), "config.md")
    if os.path.isfile(path):
        keys, _ = read_md(path)
        check_keys(keys, ("mode",), (), path)
        if "mode" in keys:
            if keys["mode"] not in MODES:
                raise ConfigError("%s: mode must be attended or away" % path)
            return keys["mode"], path
    return "attended", "default"

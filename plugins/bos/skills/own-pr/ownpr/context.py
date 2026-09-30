"""Where own-pr runs: the checkout, its GitHub repo, the origin flow, the session identity."""
import os
import re
import subprocess

URL_RE = re.compile(r"^(?:[a-z+]+://)?(?:[^@/]+@)?([^/:]+)[:/](.+?)(?:\.git)?/?$")


class ContextError(Exception):
    pass


def repo_id_from_url(url):
    m = URL_RE.match(url.strip())
    if not m or m.group(2).count("/") != 1:
        raise ContextError("cannot read host/owner/repo from remote url %r" % url)
    return "%s/%s" % (m.group(1), m.group(2))


def git(cwd, *args):
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except OSError as exc:
        raise ContextError("git %s: %s" % (" ".join(args), exc))
    if out.returncode != 0:
        raise ContextError("git %s: %s" % (" ".join(args), out.stderr.strip()))
    return out.stdout.strip()


def checkout(cwd):
    top = git(cwd, "rev-parse", "--show-toplevel")
    branch = git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    common = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    main_root = os.path.dirname(common) if os.path.basename(common) == ".git" else common
    repo = repo_id_from_url(git(cwd, "remote", "get-url", "origin"))
    return {"toplevel": os.path.realpath(top), "branch": branch, "repo": repo,
            "main_root": os.path.realpath(main_root)}


def identity(env):
    return {"claude": env.get("CLAUDE_CODE_SESSION_ID") or None,
            "codex": env.get("CODEX_THREAD_ID") or None,
            "agterm": env.get("AGTERM_SESSION_ID") or None,
            "pane": env.get("AGTERM_PANE") or None}


def resolve_origin(origins, explicit, env_value, main_root):
    name = explicit or env_value
    if name:
        if name not in origins:
            raise ContextError("unknown origin %r (no origins/%s.md)" % (name, name))
        return origins[name]
    for origin in origins.values():
        if origin.root == main_root:
            return origin
    return None

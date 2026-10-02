"""`prs`: every open run, what it owes the human, untracked PRs, and jumping to the owning session."""
import json
import re
import subprocess
import time

from . import config, engine

FAILED = ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE")
WAITING = ("", "PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", "WAITING", "REQUESTED")
HEADERS = ("PR", "REPO", "TITLE", "PROFILE", "NOW", "OWED", "CI", "ACTIVE", "SESSION")


def real_gh(args):
    try:
        out = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except ValueError:
        return None


def real_select(agterm_id):
    try:
        out = subprocess.run(["agtermctl", "session", "select", "--target", agterm_id],
                             capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0


def ci_summary(rollup):
    if not rollup:
        return "-"
    states = [(c.get("conclusion") or c.get("state") or c.get("status") or "").upper() for c in rollup]
    if any(s in FAILED for s in states):
        return "red"
    if any(s in WAITING for s in states):
        return "pending"
    return "green"


def ago(ts, now=None):
    d = int((now or time.time()) - ts)
    if d < 3600:
        return "%dm" % (d // 60)
    if d < 86400:
        return "%dh" % (d // 3600)
    return "%dd" % (d // 86400)


def label(action):
    if action.kind == "done":
        return "done"
    if action.waits:
        return "%s waits for the human" % action.step
    return "%s %s" % (action.step, {"reconcile": "running", "retry": "failed"}.get(action.kind, "next"))


def short_repo(repo_id):
    return repo_id.split("/", 1)[1]


def render(rows):
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(HEADERS))]
    return "\n".join("  ".join(str(c).ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)


def table(journal, gh):
    rows = [HEADERS]
    for run in journal.open_runs():
        info = gh(["pr", "view", run["pr_url"], "--json", "state,title,isDraft,statusCheckRollup"]) \
            if run["pr_url"] else None
        state = (info or {}).get("state")
        try:
            mode, _ = engine.effective_mode(run, config.machine_mode())
            now = label(engine.peek(journal, config.load_repo(run["repo"]), run, mode))
        except (config.ConfigError, engine.RuleError):
            now = "config error"
        if state in ("MERGED", "CLOSED"):
            now = "%s, %s" % (state.lower(), now)
        owed = journal.open_owed(run["id"])
        owed_label = ",".join(sorted({o["step"] or "other" for o in owed})) or "-"
        title = ((info or {}).get("title") or run["branch"])[:40]
        rows.append(("#%s" % run["pr_number"] if run["pr_number"] else "-",
                     short_repo(run["repo"]), title, run["profile"], now, owed_label,
                     ci_summary((info or {}).get("statusCheckRollup")), ago(run["updated"]),
                     (run["agterm_session"] or "-")[:8]))
    out = [render(rows)] if len(rows) > 1 else ["No open own-pr runs."]
    tracked = {r["pr_url"] for r in journal.open_runs() if r["pr_url"]}
    mine = gh(["search", "prs", "--author=@me", "--state=open", "--limit", "100",
               "--json", "url,title,repository"]) or []
    untracked = [p for p in mine if p["url"] not in tracked]
    if untracked:
        out += ["", "Untracked open PRs:"]
        out += ["  #%s %s  %s" % (p["url"].rsplit("/", 1)[1], p["repository"]["nameWithOwner"],
                                  p["title"]) for p in untracked]
    return "\n".join(out)


def owed_report(journal):
    out, by_run = [], {}
    for item in journal.open_owed():
        by_run.setdefault(item["run_id"], []).append(item)
    for run_id, owed in by_run.items():
        run = journal.run(run_id)
        label = "#%s" % run["pr_number"] if run["pr_number"] else short_repo(run["repo"])
        closed = ", closed" if run["state"] != "open" else ""
        out.append("%s (%s, run %s%s)" % (label, run["branch"], run["id"], closed))
        out += ["  [%d] %s" % (o["id"], o["text"]) for o in owed]
    return "\n".join(out) or "Nothing is waiting on you."


def resolve(journal, target):
    runs, t = journal.open_runs(), str(target).strip()
    matches = [r for r in runs if t in (r["id"], r["pr_url"])]
    m = re.match(r"^(?:(?P<repo>[\w.-]+/[\w.-]+)#|#)?(?P<num>\d+)$", t)
    if not matches and m:
        matches = [r for r in runs if r["pr_number"] == int(m.group("num"))
                   and (not m.group("repo") or short_repo(r["repo"]) == m.group("repo"))]
    if not matches:
        raise ValueError("no open run for %s" % t)
    if len(matches) > 1:
        raise ValueError("%s is ambiguous: %s; use owner/repo#N or the run id" % (
            t, ", ".join("%s#%s (run %s)" % (short_repo(r["repo"]), r["pr_number"], r["id"])
                         for r in matches)))
    return matches[0]


def go(journal, target, select):
    run = resolve(journal, target)
    t = str(target).strip()
    sid = run["agterm_session"]
    if not sid:
        raise ValueError("no agterm session recorded for %s (run %s)" % (t, run["id"]))
    if not select(sid):
        raise ValueError("agterm session %s for %s no longer exists" % (sid[:8], t))
    return "switched to agterm session %s" % sid[:8]


WATCHED = (("state", "state"), ("reviewDecision", "decision"), ("reviews", "reviews"), ("comments", "comments"))


def fingerprint(info):
    out = {}
    for key, label in WATCHED:
        value = info.get(key)
        out[label] = len(value) if isinstance(value, list) else (value or "-")
    return out


def watch(run, gh, sleep, interval):
    """Block until the PR's state, review decision, reviews or comments change; say what changed."""
    base = None
    while True:
        info = gh(["pr", "view", run["pr_url"], "--json", "state,reviewDecision,reviews,comments"])
        if info is not None:
            now = fingerprint(info)
            if base is None:
                base = now
            elif now != base:
                return ", ".join("%s %s -> %s" % (k, base[k], now[k]) for k in now if now[k] != base[k])
        sleep(interval)


def real_type(session, pane, text):
    args = ["agtermctl", "session", "type", "--target", session, text]
    if pane:
        args[4:4] = ["--pane", pane]
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=15).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def notify(run, change, typer):
    return nudge(run, "changed (%s)" % change, typer)


def nudge(run, message, typer):
    text = "own-pr: %s %s. Run `own-pr next`.\n" % (run["pr_url"] or run["branch"], message)
    return typer(run["agterm_session"], run["agterm_pane"], text)

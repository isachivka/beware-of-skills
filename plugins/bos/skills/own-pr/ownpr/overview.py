"""`prs`: every open run, what it owes Igor, untracked PRs, and jumping to the owning session."""
import json
import re
import subprocess
import time

from . import config, engine

FAILED = ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE")
WAITING = ("", "PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", "WAITING", "REQUESTED")
HEADERS = ("PR", "REPO", "TITLE", "PROFILE", "NOW", "OWED", "CI", "RC", "ACTIVE", "SESSION")


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


def now_label(states, order):
    for sid in order:
        if states.get(sid, {}).get("status") == "running":
            return "%s running" % sid
    for sid in order:
        status = states.get(sid, {}).get("status", "pending")
        if status == "failed":
            return "%s failed" % sid
        if status == "pending":
            return "%s next" % sid
    return "done"


def short_repo(repo_id):
    return repo_id.split("/", 1)[1]


def render(rows):
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(HEADERS))]
    return "\n".join("  ".join(str(c).ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)


def table(journal, gh):
    rows, notes = [HEADERS], []
    for run in journal.open_runs():
        info = gh(["pr", "view", run["pr_url"], "--json", "state,title,isDraft,statusCheckRollup"]) \
            if run["pr_url"] else None
        states = journal.steps(run["id"])
        state = (info or {}).get("state")
        if state in ("MERGED", "CLOSED"):
            running = [s for s, v in states.items() if v["status"] == "running"]
            if not running:
                journal.close_run(run["id"])
                notes.append("closed run %s: PR is %s" % (run["id"], state.lower()))
                continue
        try:
            order = engine.profile_steps(config.load_repo(run["repo"]), run)
            now = now_label(states, order)
        except (config.ConfigError, engine.RuleError):
            now = "config error"
        if state in ("MERGED", "CLOSED"):
            now = "%s, %s" % (state.lower(), now)
        owed = journal.open_owed(run["id"])
        owed_label = ",".join(sorted({o["step"] or "other" for o in owed})) or "-"
        title = ((info or {}).get("title") or run["branch"])[:40]
        rc = ",".join(c["env"] for c in journal.claims(run["id"])) or "-"
        rows.append(("#%s" % run["pr_number"] if run["pr_number"] else "-",
                     short_repo(run["repo"]), title, run["profile"], now, owed_label,
                     ci_summary((info or {}).get("statusCheckRollup")), rc, ago(run["updated"]),
                     (run["agterm_session"] or "-")[:8]))
    out = [render(rows)] if len(rows) > 1 else ["No open own-pr runs."]
    out += notes
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
    out = []
    for run in journal.open_runs():
        owed = journal.open_owed(run["id"])
        if not owed:
            continue
        label = "#%s" % run["pr_number"] if run["pr_number"] else short_repo(run["repo"])
        out.append("%s (%s, run %s)" % (label, run["branch"], run["id"]))
        out += ["  [%d] %s" % (o["id"], o["text"]) for o in owed]
    return "\n".join(out) or "Nothing is waiting on you."


def go(journal, target, select):
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
    run = matches[0]
    sid = run["agterm_session"]
    if not sid:
        raise ValueError("no agterm session recorded for %s (run %s)" % (t, run["id"]))
    if not select(sid):
        raise ValueError("agterm session %s for %s no longer exists" % (sid[:8], t))
    return "switched to agterm session %s" % sid[:8]

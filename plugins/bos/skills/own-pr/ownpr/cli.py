"""The `own-pr` command line. `prs` is the same program under another name (see overview.py)."""
import argparse
import json
import os
import re
import sqlite3
import sys

from . import config, context, engine
from .journal import Journal, JournalError

PR_URL_RE = re.compile(r"^https?://([^/]+)/([^/]+/[^/]+)/pull/(\d+)/?$")


class Fail(Exception):
    pass


ERRORS = (config.ConfigError, context.ContextError, JournalError, engine.RuleError, Fail,
          OSError, sqlite3.Error, UnicodeError)


def open_journal():
    return Journal(os.path.join(config.state_dir(), "own-pr.db"))


def current_run(j, args):
    if getattr(args, "run", None):
        run = j.run(args.run)
        if run["state"] != "open":
            raise Fail("run %s is closed" % run["id"])
        return run
    co = context.checkout(os.getcwd())
    run = j.find_open_run(co["repo"], co["branch"])
    if not run:
        raise Fail("no open run for %s %s here; start one with `own-pr start`" % (co["repo"], co["branch"]))
    return run


def run_mode(run):
    return engine.effective_mode(run, config.machine_mode())


def choose_profile(repo, origin, args):
    if args.profile:
        if args.profile not in repo.profiles:
            why = "; ".join(repo.invalid.get(args.profile, ["not found"]))
            raise Fail("no valid profile %r in %s: %s" % (args.profile, repo.id, why))
        return args.profile, ("agent" if args.auto_reason else "explicit")
    if origin and repo.id in origin.profiles:
        name = origin.profiles[repo.id]
        if name not in repo.profiles:
            raise Fail("origin %s names profile %r, which is not valid in %s" % (origin.name, name, repo.id))
        return name, "origin"
    if repo.default != "auto":
        return repo.default, "repo default"
    lines = ["%s has `default: auto`: choose a profile and rerun with"
             " --profile NAME --auto-reason WHY (or the one the human named, without --auto-reason):" % repo.id]
    lines += ["  %s: %s" % (p.name, p.description) for p in repo.profiles.values()]
    raise Fail("\n".join(lines))


def cmd_start(args, j):
    co = context.checkout(os.getcwd())
    repo = config.load_repo(co["repo"])
    origin = context.resolve_origin(config.load_origins(), args.origin,
                                    os.environ.get("OWN_PR_ORIGIN"), co["main_root"])
    profile, by = choose_profile(repo, origin, args)
    mode_env = os.environ.get("OWN_PR_MODE") or None
    if mode_env and mode_env not in config.MODES:
        raise Fail("OWN_PR_MODE must be attended or away, got %r" % mode_env)
    run_id = j.create_run(co["repo"], co["branch"], co["toplevel"], profile, by,
                          repo.profiles[profile].steps, origin=origin.name if origin else None,
                          mode_env=mode_env, identity=context.identity(os.environ))
    if by == "agent":
        j.add_owed(run_id, "profile %s chosen by the agent: %s" % (profile, args.auto_reason))
    print("run %s: %s %s, profile %s (%s), origin %s"
          % (run_id, co["repo"], co["branch"], profile, by, origin.name if origin else "none"))
    return 0


def cmd_bind(args, j):
    run = current_run(j, args)
    m = PR_URL_RE.match(args.url.strip())
    if not m:
        raise Fail("not a pull request url: %r" % args.url)
    repo_id = "%s/%s" % (m.group(1), m.group(2))
    if repo_id != run["repo"]:
        raise Fail("%s belongs to %s, but this run is for %s" % (args.url, repo_id, run["repo"]))
    j.update_run(run["id"], pr_url=args.url.strip(), pr_number=int(m.group(3)))
    print("run %s bound to %s" % (run["id"], args.url))
    return 0


def render_action(action, repo, run, origin, added, evidence=None):
    lines = ["NEW: step %s was added to profile %s since this run started" % (s, run["profile"])
             for s in added]
    if action.kind == "done":
        lines.append("NEXT: done — every step of profile %s is finished" % run["profile"])
        return "\n".join(lines)
    step = repo.steps.get(action.step)
    kind = step.kind if step else "removed"
    body = step.body if step else ("This step is no longer in the profile config. Find out how it "
                                   "ended and record done or failed.")
    extra = ""
    if action.auto_pick:
        extra = ", agent decides — record done with --note; it becomes owed to the human"
    elif action.waits:
        extra = ", the human's step — ask them and wait"
    lines.append("NEXT: %s %s  (kind=%s, mode=%s%s)" % (action.kind, action.step, kind,
                                                         action.mode, extra))
    if action.kind == "reconcile":
        lines.append("This step is marked running: find out whether it finished, then record done or failed.")
    if action.kind == "retry":
        lines.append("This step failed last time: fix the cause, then run it again.")
    lines.append("PR: %s" % (run["pr_url"] or "(none yet)"))
    if origin and origin.notes:
        lines.append("Origin %s: %s" % (origin.name, origin.notes))
    if evidence:
        lines.append("Evidence so far: %s" % evidence)
    lines += ["", body]
    return "\n".join(lines)


def run_origin(run):
    return config.load_origins().get(run["origin"]) if run["origin"] else None


def cmd_next(args, j):
    run = current_run(j, args)
    repo = config.load_repo(run["repo"])
    mode, source = run_mode(run)
    added = [s for s in engine.profile_steps(repo, run) if s not in j.steps(run["id"])]
    action = engine.next_action(j, repo, run, mode, mode_source=source)
    evidence = j.steps(run["id"]).get(action.step, {}).get("evidence") if action.step else None
    print(render_action(action, repo, j.run(run["id"]), run_origin(run), added, evidence))
    return 0


def cmd_step(args, j):
    run = current_run(j, args)
    repo = config.load_repo(run["repo"])
    mode, source = run_mode(run)
    engine.record_step(j, repo, run, args.step, args.status, mode, evidence=args.evidence,
                       note=args.note, by_human=args.by_human, mode_source=source)
    print("%s: %s" % (args.step, args.status))
    return 0


def cmd_owe(args, j):
    run = current_run(j, args)
    owed_id = j.add_owed(run["id"], args.text, step=args.step)
    print("owed #%d: %s" % (owed_id, args.text))
    return 0


def cmd_clear(args, j):
    run = current_run(j, args)
    engine.clear_owed(j, run, args.owed_id, by_human=args.by_human)
    print("cleared #%d" % args.owed_id)
    return 0


def cmd_profile(args, j):
    run = current_run(j, args)
    added, removed = engine.switch_profile(j, config.load_repo(run["repo"]), run, args.name,
                                           args.by_human)
    print("profile %s -> %s; added: %s; removed: %s" % (run["profile"], args.name,
                                                        ", ".join(added) or "-", ", ".join(removed) or "-"))
    return 0


def cmd_mode(args, j):
    run = current_run(j, args)
    j.update_run(run["id"], mode_run=None if args.mode == "clear" else args.mode)
    print("run %s mode: %s" % (run["id"], run_mode(j.run(run["id"]))[0]))
    return 0


def cmd_machine(args, j):
    state = config.state_dir()
    os.makedirs(state, exist_ok=True)
    with open(os.path.join(state, "mode"), "w") as fh:
        fh.write(args.cmd + "\n")
    print("machine mode: %s" % args.cmd)
    for run in j.open_runs():
        mode, source = run_mode(run)
        if mode != args.cmd:
            print("  run %s (%s %s) stays %s (%s)" % (run["id"], run["repo"], run["branch"], mode, source))
    return 0


def cmd_explain(args, j):
    run = None
    try:
        run = current_run(j, args)
        repo_id = run["repo"]
    except Fail:
        repo_id = context.checkout(os.getcwd())["repo"]
    repo = config.load_repo(repo_id)
    out = ["repo: %s  (%s)" % (repo.id, repo.source),
           "requires: %s" % (", ".join(repo.requires) or "-"),
           "default profile: %s" % repo.default,
           "profiles: %s" % ", ".join(repo.profiles)]
    out += ["invalid profile %s: %s" % (n, "; ".join(e)) for n, e in repo.invalid.items()]
    if run:
        mode, source = run_mode(run)
        out += ["run: %s" % run["id"],
                "profile: %s (%s)" % (run["profile"], run["profile_by"]),
                "origin: %s" % (run["origin"] or "none"),
                "origin notes: %s" % (getattr(run_origin(run), "notes", "") or "none"),
                "mode: %s (%s)" % (mode, source),
                "steps:"]
        states = j.steps(run["id"])
        for sid in engine.profile_steps(repo, run):
            step, state = repo.steps[sid], states.get(sid, {})
            line = "  %s  kind=%s away=%s  status=%s  (%s)" % (sid, step.kind, step.away,
                                                              state.get("status", "pending"), step.source)
            if state.get("evidence"):
                line += "  evidence=%s" % state["evidence"]
            out.append(line)
    print("\n".join(out))
    return 0


def cmd_env(args, j):
    run = current_run(j, args)
    if args.action == "claim":
        j.claim(args.env, run["id"])
    else:
        j.release(args.env, run["id"])
    print("%s %sed by run %s" % (args.env, args.action, run["id"]))
    return 0


def cmd_adopt(args, j):
    if j.run(args.target)["state"] != "open":
        raise Fail("run %s is closed" % args.target)
    ident = context.identity(os.environ)
    j.update_run(args.target, claude_session=ident["claude"], codex_session=ident["codex"],
                 agterm_session=ident["agterm"])
    print("run %s now owned by this session" % args.target)
    return 0


def cmd_close(args, j):
    run = current_run(j, args)
    engine.close(j, run)
    print("run %s closed" % run["id"])
    return 0


def cmd_export(args, j):
    print(json.dumps(j.export(), indent=2, ensure_ascii=False))
    return 0


def own_pr_parser():
    ap = argparse.ArgumentParser(prog="own-pr", description="Drive your own pull requests.")
    ap.add_argument("--run", help="run id (default: the open run for this checkout)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start")
    p.add_argument("--profile")
    p.add_argument("--auto-reason")
    p.add_argument("--origin")
    p.set_defaults(fn=cmd_start)
    p = sub.add_parser("bind")
    p.add_argument("url")
    p.set_defaults(fn=cmd_bind)
    sub.add_parser("next").set_defaults(fn=cmd_next)
    p = sub.add_parser("step")
    p.add_argument("step")
    p.add_argument("status", choices=("pending", "running", "done", "failed", "skipped", "deferred"))
    p.add_argument("--evidence")
    p.add_argument("--note")
    p.add_argument("--by-human", action="store_true")
    p.set_defaults(fn=cmd_step)
    p = sub.add_parser("owe")
    p.add_argument("text")
    p.add_argument("--step")
    p.set_defaults(fn=cmd_owe)
    p = sub.add_parser("clear")
    p.add_argument("owed_id", type=int)
    p.add_argument("--by-human", action="store_true")
    p.set_defaults(fn=cmd_clear)
    p = sub.add_parser("profile")
    p.add_argument("name")
    p.add_argument("--by-human", action="store_true")
    p.set_defaults(fn=cmd_profile)
    p = sub.add_parser("mode")
    p.add_argument("mode", choices=("attended", "away", "clear"))
    p.set_defaults(fn=cmd_mode)
    sub.add_parser("away").set_defaults(fn=cmd_machine)
    sub.add_parser("attended").set_defaults(fn=cmd_machine)
    sub.add_parser("explain").set_defaults(fn=cmd_explain)
    p = sub.add_parser("env")
    p.add_argument("action", choices=("claim", "release"))
    p.add_argument("env")
    p.set_defaults(fn=cmd_env)
    p = sub.add_parser("adopt")
    p.add_argument("target")
    p.set_defaults(fn=cmd_adopt)
    sub.add_parser("close").set_defaults(fn=cmd_close)
    sub.add_parser("export").set_defaults(fn=cmd_export)
    return ap


def prs_main(argv):
    from . import overview
    ap = argparse.ArgumentParser(prog="prs", description="Your own PRs in flight.")
    ap.add_argument("--no-gh", action="store_true", help="do not ask GitHub")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("owed")
    p = sub.add_parser("go")
    p.add_argument("pr", help="N, #N, owner/repo#N, PR url or run id")
    args = ap.parse_args(argv)
    try:
        j = open_journal()
        if args.cmd == "owed":
            print(overview.owed_report(j))
        elif args.cmd == "go":
            print(overview.go(j, args.pr, overview.real_select))
        else:
            print(overview.table(j, (lambda a: None) if args.no_gh else overview.real_gh))
    except (ValueError,) + ERRORS as exc:
        print("prs: %s" % exc, file=sys.stderr)
        return 2
    return 0


def main(argv=None, prog=None):
    argv = sys.argv[1:] if argv is None else argv
    prog = prog or os.path.basename(sys.argv[0])
    if prog == "prs":
        return prs_main(argv)
    parser = own_pr_parser()
    args = parser.parse_args(argv)
    try:
        return args.fn(args, open_journal())
    except ERRORS as exc:
        print("own-pr: %s" % exc, file=sys.stderr)
        return 2

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
    with j.tx():
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
    url = "https://%s/%s/pull/%s" % (m.group(1), m.group(2), m.group(3))
    j.update_run(run["id"], pr_url=url, pr_number=int(m.group(3)))
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
    # an owed item names its run, and debt outlives a closed run
    run = j.run(j.owed(args.owed_id)["run_id"])
    if getattr(args, "run", None) and args.run != run["id"]:
        raise Fail("owed item %s belongs to run %s" % (args.owed_id, run["id"]))
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
        try:
            order = engine.profile_steps(repo, run)
        except engine.RuleError:
            print("\n".join(out))
            raise
        for sid in order:
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


OWN_PR_EPILOG = """\
how it works:
  The process lives in ~/.config/own-pr (or $OWN_PR_CONFIG_DIR) as Markdown: a step library,
  per-repo profiles (ordered step lists) and origins (the flows work comes from). The agent
  that did the work drives the PR in its own session:

    own-pr start                     once per branch; picks the profile
    own-pr next                      what to do now, with that step's instructions
    own-pr step <id> done|failed     record what actually happened; repeat `next`

  Steps are `auto` (the agent does them) or `human` (the human does them). In `away` mode
  every step runs except human ones: those are deferred or decided by the agent and pile up
  as owed items, and steps marked `away: wait` stop the pipeline until the human is back.

  State: ~/.local/state/own-pr/own-pr.db (or $OWN_PR_STATE_DIR). Overview: `prs`.

examples:
  own-pr start --profile quick
  own-pr step ci running
  own-pr step ci done --evidence https://github.com/o/r/actions/runs/1
  own-pr step manual-check skipped --by-human --note "no UI change"
  own-pr away                        leaving: defer human steps on every PR
"""

STEP_HELP = """\
Record the outcome of a step of this run's profile.

statuses:
  pending   must run (again); forgets the old evidence. Use it to re-queue a finished step.
  running   started and not finished yet: long waits, deploys, test runs. `next` will ask
            you to reconcile it if the session stops.
  done      finished and verified. A human step needs --by-human, except an agent-made
            decision in away mode (needs --note; becomes owed to the human).
  failed    tried and did not work; `next` sends you back to retry it.
  skipped   the human decided not to do it: needs --by-human and --note with their reason.
            Steps the repo requires cannot be skipped.
"""


def own_pr_parser():
    raw = argparse.RawDescriptionHelpFormatter
    ap = argparse.ArgumentParser(
        prog="own-pr", formatter_class=raw, epilog=OWN_PR_EPILOG,
        description="Drive your own pull request through a process defined as text.")
    ap.add_argument("--run", metavar="ID",
                    help="act on this run instead of the open run for the current checkout")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="<command>")

    def cmd(name, fn, summary, description=None):
        p = sub.add_parser(name, help=summary, description=description or summary,
                           formatter_class=raw)
        p.set_defaults(fn=fn)
        return p

    p = cmd("start", cmd_start, "create a run for this checkout and pick its profile",
            "Create a run for the current checkout's repo and branch. The profile comes from\n"
            "--profile, else the origin's profile for this repo, else repo.md `default`. With\n"
            "`default: auto` the list of profiles is printed: choose one and pass it again.")
    p.add_argument("--profile", metavar="NAME", help="profile to use (named by the human or the calling flow)")
    p.add_argument("--auto-reason", metavar="WHY",
                   help="the agent picked --profile itself: why (becomes owed to the human)")
    p.add_argument("--origin", metavar="NAME",
                   help="flow the work came from (default: $OWN_PR_ORIGIN, else matched by `root:`)")
    p = cmd("bind", cmd_bind, "attach the pull request to the run")
    p.add_argument("url", help="https://<host>/<owner>/<repo>/pull/<N>; must be this run's repo")
    cmd("next", cmd_next, "print the next action and that step's instructions",
        "Print NEXT: <action> <step>, the PR, origin notes, and the step's prose.\n"
        "actions: do (run it), retry (it failed), reconcile (it was running when the session\n"
        "stopped: find out how it ended), done (profile finished). In away mode `next` itself\n"
        "defers human steps that allow it.")
    p = cmd("step", cmd_step, "record a step's outcome: pending|running|done|failed|skipped", STEP_HELP)
    p.add_argument("step", help="step id, as listed by `own-pr explain`")
    p.add_argument("status", choices=("pending", "running", "done", "failed", "skipped"))
    p.add_argument("--evidence", metavar="URL", help="link proving it: PR, CI run, deploy, Slack post")
    p.add_argument("--note", metavar="TEXT", help="what happened; required for skips and agent decisions")
    p.add_argument("--by-human", action="store_true",
                   help="the human did or decided this, in this session")
    p = cmd("owe", cmd_owe, "add something the human should look at (shown in `prs owed`)")
    p.add_argument("text")
    p.add_argument("--step", metavar="ID", help="step it belongs to; done --by-human on that step clears it")
    p = cmd("clear", cmd_clear, "the human has looked at an owed item",
            "Discharge an owed item. Only the human does this: fixing what the item\n"
            "describes does not clear it. Ids are listed by `prs owed`.")
    p.add_argument("owed_id", type=int, metavar="ID")
    p.add_argument("--by-human", action="store_true", help="required: the human looked at it")
    p = cmd("profile", cmd_profile, "switch this run to another profile",
            "Switch profile; prints added and removed steps. Owed items and claims survive.\n"
            "Without --by-human, dropping steps becomes owed to the human.")
    p.add_argument("name")
    p.add_argument("--by-human", action="store_true", help="the human asked for this profile")
    p = cmd("mode", cmd_mode, "set this run's mode (the human's decision in this session)",
            "Override the mode for this run only: attended, away, or clear to follow the\n"
            "terminal ($OWN_PR_MODE at start) and machine mode again.")
    p.add_argument("mode", choices=("attended", "away", "clear"))
    cmd("away", cmd_machine, "machine mode: defer human steps on every run",
        "Set the machine-wide mode to away. Runs with a terminal or run override keep theirs;\n"
        "they are listed.")
    cmd("attended", cmd_machine, "machine mode: human steps wait for the human again")
    cmd("explain", cmd_explain, "show the resolved steps and settings with their source files")
    p = cmd("env", cmd_env, "claim or release a shared resource for this run",
            "A claim fails while another open run holds the resource. Closing the run\n"
            "releases its claims.")
    p.add_argument("action", choices=("claim", "release"))
    p.add_argument("env", metavar="NAME", help="resource name, as the step prose uses it")
    p = cmd("adopt", cmd_adopt, "make this session the owner of a run another session started")
    p.add_argument("target", metavar="RUN", help="run id, as shown by `prs`")
    cmd("close", cmd_close, "end the run (refused while a step is running)")
    cmd("export", cmd_export, "print the whole journal as JSON")
    return ap


def prs_main(argv):
    from . import overview
    ap = argparse.ArgumentParser(
        prog="prs", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Your own PRs in flight: one row per open own-pr run (PR, profile, what it is\n"
                    "doing now, what it owes the human, CI, last activity, owning terminal), then\n"
                    "your open PRs that no run tracks.",
        epilog="examples:\n  prs\n  prs owed\n  prs go 13300                 by number, if it is unique\n"
               "  prs go owner/repo#N          when two repos share a number\n")
    ap.add_argument("--no-gh", action="store_true", help="do not ask GitHub (offline, faster)")
    sub = ap.add_subparsers(dest="cmd", metavar="<command>")
    sub.add_parser("owed", help="everything waiting on the human, with ids for `own-pr clear`")
    p = sub.add_parser("go", help="switch to the agterm session that owns a PR")
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

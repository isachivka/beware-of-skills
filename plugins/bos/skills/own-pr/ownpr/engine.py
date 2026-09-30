"""own-pr rules: effective mode, the next step, recording outcomes. Knows no step by name."""
from dataclasses import dataclass


class RuleError(Exception):
    pass


@dataclass
class Action:
    kind: str
    step: str = None
    mode: str = None
    auto_pick: bool = False
    waits: bool = False


def effective_mode(run, machine):
    if run.get("mode_run"):
        return run["mode_run"], "run (set in session)"
    if run.get("mode_env"):
        return run["mode_env"], "terminal OWN_PR_MODE"
    return machine


def profile_steps(repo, run):
    profile = repo.profiles.get(run["profile"])
    if not profile:
        why = "; ".join(repo.invalid.get(run["profile"], ["not found"]))
        raise RuleError("profile %s of %s is not usable: %s" % (run["profile"], repo.id, why))
    return profile.steps


def running_steps(journal, run):
    return [s for s, v in journal.steps(run["id"]).items() if v["status"] == "running"]


def mode_label(mode, source):
    return "%s (%s)" % (mode, source) if source else mode


def peek(journal, repo, run, mode):
    """The next action without side effects; `next_action` applies the away-mode deferrals."""
    order = profile_steps(repo, run)
    states = journal.steps(run["id"])
    if mode == "attended":
        # the human is back: deferred work goes to them even while a long step (a CI or review
        # wait) is still running
        for sid in order:
            if states.get(sid, {}).get("status") == "deferred":
                return Action("do", sid, mode, waits=repo.steps[sid].kind == "human")
    # a step dropped from the profile while it was running still has to be reconciled
    running = [s for s in order if states.get(s, {}).get("status") == "running"]
    running += [s for s, v in states.items() if v["status"] == "running" and s not in order]
    if running:
        return Action("reconcile", running[0], mode)
    for sid in order:
        status, step = states.get(sid, {}).get("status", "pending"), repo.steps[sid]
        if status in ("done", "skipped"):
            continue
        if status == "failed":
            return Action("retry", sid, mode)
        if status == "deferred" and mode == "away":
            continue
        if step.kind == "human":
            if mode == "away" and step.away == "defer":
                continue
            if mode == "away" and step.away == "auto-pick":
                return Action("do", sid, mode, auto_pick=True)
            return Action("do", sid, mode, waits=True)
        return Action("do", sid, mode)
    return Action("done", None, mode)


def next_action(journal, repo, run, mode, mode_source=None):
    order = profile_steps(repo, run)
    journal.ensure_steps(run["id"], order)
    action = peek(journal, repo, run, mode)
    if mode != "away" or action.kind == "reconcile":
        return action
    states = journal.steps(run["id"])
    stop = order.index(action.step) if action.step in order else len(order)
    for sid in order[:stop]:
        step = repo.steps[sid]
        if states[sid]["status"] == "pending" and step.kind == "human" and step.away == "defer":
            with journal.tx():
                journal.set_step(run["id"], sid, "deferred", note="deferred while away", by="agent",
                                 mode=mode_label(mode, mode_source))
                journal.add_owed(run["id"], "%s deferred while you were away" % sid, step=sid)
    return action


def record_step(journal, repo, run, step_id, status, mode, evidence=None, note=None, by_human=False,
                mode_source=None):
    order = profile_steps(repo, run)
    in_flight = journal.steps(run["id"]).get(step_id, {}).get("status") == "running"
    if step_id not in order and not (in_flight and status in ("done", "failed")):
        raise RuleError("step %r is not in profile %s" % (step_id, run["profile"]))
    step, by = repo.steps.get(step_id), ("human" if by_human else "agent")
    label = mode_label(mode, mode_source)
    if status == "deferred":
        raise RuleError("deferral is decided by `own-pr next`, not recorded by hand")
    if status == "skipped":
        if not by_human:
            raise RuleError("only the human skips a step; record it with --by-human once they have said so")
        if not note:
            raise RuleError("a skip needs --note with the human's reason")
        journal.set_step(run["id"], step_id, "skipped", evidence, note, by, mode=label)
        return
    if status == "done" and step and step.kind == "human":
        if by_human:
            journal.set_step(run["id"], step_id, "done", evidence, note, by, mode=label)
            journal.clear_owed_for_step(run["id"], step_id)
            return
        if step.away == "auto-pick" and mode == "away":
            if not note:
                raise RuleError("an agent-made decision needs --note with what was chosen and why")
            with journal.tx():
                journal.set_step(run["id"], step_id, "done", evidence, note, by, mode=label)
                journal.add_owed(run["id"], "%s decided by the agent: %s" % (step_id, note), step=step_id)
            return
        raise RuleError("%s is the human's step; record done with --by-human once they have done it" % step_id)
    journal.set_step(run["id"], step_id, status, evidence, note, by, mode=label)


def clear_owed(journal, run, owed_id, by_human=False):
    if not by_human:
        raise RuleError("only the human discharges an owed item; record it with --by-human once they have looked")
    item = journal.owed(owed_id)
    if item["run_id"] != run["id"]:
        raise RuleError("owed item %s belongs to run %s" % (owed_id, item["run_id"]))
    with journal.tx():
        journal.clear_owed(owed_id)
        step = item["step"]
        if step and journal.steps(run["id"]).get(step, {}).get("status") == "deferred":
            journal.set_step(run["id"], step, "done", note="cleared by the human", by="human")


def switch_profile(journal, repo, run, name, by_human):
    if name not in repo.profiles:
        why = "; ".join(repo.invalid.get(name, ["not found"]))
        raise RuleError("no valid profile %r in %s: %s" % (name, repo.id, why))
    old = profile_steps(repo, run)
    busy = [s for s in running_steps(journal, run) if s in old]
    if busy:
        raise RuleError("%s is running; let it finish before switching profile" % ", ".join(busy))
    new = repo.profiles[name].steps
    added = [s for s in new if s not in old]
    removed = [s for s in old if s not in new]
    with journal.tx():
        journal.ensure_steps(run["id"], new)
        journal.update_run(run["id"], profile=name, profile_by="explicit" if by_human else "agent")
        if removed and not by_human:
            journal.add_owed(run["id"], "agent switched profile %s -> %s, dropping %s"
                             % (run["profile"], name, ", ".join(removed)))
    return added, removed


def close(journal, run):
    busy = running_steps(journal, run)
    if busy:
        raise RuleError("%s is running; reconcile it before closing" % ", ".join(busy))
    journal.close_run(run["id"])

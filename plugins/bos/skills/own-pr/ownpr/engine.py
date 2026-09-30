"""own-pr rules: effective mode, the next step, recording outcomes, the team-handoff barrier."""
from dataclasses import dataclass, field


class RuleError(Exception):
    pass


@dataclass
class Action:
    kind: str
    step: str = None
    mode: str = None
    auto_pick: bool = False
    blockers: list = field(default_factory=list)


def effective_mode(run, machine):
    if run.get("mode_run"):
        return run["mode_run"], "run (Igor in session)"
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


def handoff_blockers(journal, repo, run):
    order = profile_steps(repo, run)
    if "team-handoff" not in order:
        return ["profile %s has no team-handoff step" % run["profile"]]
    states = journal.steps(run["id"])
    blockers = []
    eyeball = states.get("eyeball", {})
    # the one fact no step file can redefine: Igor himself looked, or waived it
    if eyeball.get("by") != "igor" or eyeball.get("status") not in ("done", "skipped"):
        blockers.append("Igor has not inspected the PR (eyeball) or waived it")
    for sid in order[:order.index("team-handoff")]:
        if sid == "eyeball":
            continue
        state = states.get(sid, {"status": "pending", "by": None})
        status, by = state["status"], state["by"]
        if status == "skipped" and by != "igor":
            blockers.append("%s was skipped without Igor" % sid)
        elif status not in ("done", "skipped"):
            blockers.append("%s is %s" % (sid, status))
    blockers += ["owed to Igor: %s" % o["text"] for o in journal.open_owed(run["id"])]
    return blockers


def mode_label(mode, source):
    return "%s (%s)" % (mode, source) if source else mode


def next_action(journal, repo, run, mode, mode_source=None):
    order = profile_steps(repo, run)
    journal.ensure_steps(run["id"], order)
    states = journal.steps(run["id"])
    # a step dropped from the profile while it was running still has to be reconciled
    running = [s for s in order if states[s]["status"] == "running"]
    running += [s for s, v in states.items() if v["status"] == "running" and s not in order]
    if running:
        return Action("reconcile", running[0], mode)
    for sid in order:
        status, step = states[sid]["status"], repo.steps[sid]
        if status in ("done", "skipped"):
            continue
        if sid == "team-handoff":
            blockers = handoff_blockers(journal, repo, run)
            if blockers:
                return Action("blocked", sid, mode, blockers=blockers)
        if status == "failed":
            return Action("retry", sid, mode)
        if status == "deferred":
            if mode == "attended":
                return Action("do", sid, mode)
            continue
        if mode == "away" and step.kind == "human":
            if step.away == "defer":
                journal.set_step(run["id"], sid, "deferred", note="deferred while away", by="agent",
                                 mode=mode_label(mode, mode_source))
                journal.add_owed(run["id"], "%s deferred while you were away" % sid, step=sid)
                continue
            if step.away == "auto-pick":
                return Action("do", sid, mode, auto_pick=True)
        return Action("do", sid, mode)
    return Action("done", None, mode)


def record_step(journal, repo, run, step_id, status, mode, evidence=None, note=None, by_igor=False,
                mode_source=None):
    order = profile_steps(repo, run)
    in_flight = journal.steps(run["id"]).get(step_id, {}).get("status") == "running"
    if step_id not in order and not (in_flight and status in ("done", "failed")):
        raise RuleError("step %r is not in profile %s" % (step_id, run["profile"]))
    step, by = repo.steps.get(step_id), ("igor" if by_igor else "agent")
    label = mode_label(mode, mode_source)
    if status == "deferred":
        raise RuleError("deferral is decided by `own-pr next`, not recorded by hand")
    if step_id == "team-handoff" and status in ("running", "done"):
        blockers = handoff_blockers(journal, repo, run)
        if blockers:
            raise RuleError("team handoff is blocked: %s" % "; ".join(blockers))
    if status == "skipped":
        if not by_igor:
            raise RuleError("only Igor skips a step; record it with --by-igor once he has said so")
        if step_id in repo.requires:
            raise RuleError("%s is required by %s and cannot be skipped" % (step_id, repo.id))
        if not note:
            raise RuleError("a skip needs --note with Igor's reason")
        journal.set_step(run["id"], step_id, "skipped", evidence, note, by, mode=label)
        return
    if status == "done" and step and step.kind == "human":
        if by_igor:
            journal.set_step(run["id"], step_id, "done", evidence, note, by, mode=label)
            journal.clear_owed_for_step(run["id"], step_id)
            return
        if step.away == "auto-pick" and mode == "away":
            if not note:
                raise RuleError("an agent-made decision needs --note with what was chosen and why")
            journal.set_step(run["id"], step_id, "done", evidence, note, by, mode=label)
            journal.add_owed(run["id"], "%s decided by the agent: %s" % (step_id, note), step=step_id)
            return
        raise RuleError("%s is Igor's step; record done with --by-igor once he has done it" % step_id)
    journal.set_step(run["id"], step_id, status, evidence, note, by, mode=label)


def clear_owed(journal, run, owed_id, by_igor=False):
    if not by_igor:
        raise RuleError("only Igor discharges an owed item; record it with --by-igor once he has looked")
    item = journal.owed(owed_id)
    if item["run_id"] != run["id"]:
        raise RuleError("owed item %s belongs to run %s" % (owed_id, item["run_id"]))
    journal.clear_owed(owed_id)
    step = item["step"]
    if step and journal.steps(run["id"]).get(step, {}).get("status") == "deferred":
        journal.set_step(run["id"], step, "done", note="cleared by Igor", by="igor")


def waive(journal, repo, run, by_igor=False):
    if not by_igor:
        raise RuleError("only Igor waives his review; record it with --by-igor once he has said so")
    record_step(journal, repo, run, "eyeball", "skipped", "attended", note="waived by Igor",
                by_igor=True)
    journal.clear_owed_for_step(run["id"], "eyeball")


def switch_profile(journal, repo, run, name, by_igor):
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
    journal.ensure_steps(run["id"], new)
    journal.update_run(run["id"], profile=name, profile_by="explicit" if by_igor else "agent")
    if removed and not by_igor:
        journal.add_owed(run["id"], "agent switched profile %s -> %s, dropping %s"
                         % (run["profile"], name, ", ".join(removed)))
    return added, removed


def close(journal, run):
    busy = running_steps(journal, run)
    if busy:
        raise RuleError("%s is running; reconcile it before closing" % ", ".join(busy))
    journal.close_run(run["id"])

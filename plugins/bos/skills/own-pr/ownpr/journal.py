"""The own-pr journal: runs, step states, owed items, environment claims, events."""
import contextlib
import json
import os
import sqlite3
import time
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, repo TEXT NOT NULL, branch TEXT NOT NULL, checkout TEXT NOT NULL,
  pr_url TEXT, pr_number INTEGER, origin TEXT, profile TEXT NOT NULL, profile_by TEXT NOT NULL,
  mode_env TEXT, mode_run TEXT, claude_session TEXT, codex_session TEXT, agterm_session TEXT,
  state TEXT NOT NULL DEFAULT 'open', created REAL NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS steps (
  run_id TEXT NOT NULL, step TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0, evidence TEXT, note TEXT, by TEXT, updated REAL,
  PRIMARY KEY (run_id, step));
CREATE TABLE IF NOT EXISTS owed (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, step TEXT, text TEXT NOT NULL,
  created REAL NOT NULL, cleared REAL);
CREATE TABLE IF NOT EXISTS claims (
  env TEXT PRIMARY KEY, run_id TEXT NOT NULL, claimed REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, ts REAL NOT NULL, kind TEXT NOT NULL,
  data TEXT);
"""
STATUSES = ("pending", "running", "done", "failed", "deferred", "skipped")
UPDATABLE = ("pr_url", "pr_number", "profile", "profile_by", "mode_run",
             "claude_session", "codex_session", "agterm_session")


class JournalError(Exception):
    pass


class Journal:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path, timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    @contextlib.contextmanager
    def tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    def _event(self, run_id, kind, **data):
        self.db.execute("INSERT INTO events (run_id, ts, kind, data) VALUES (?, ?, ?, ?)",
                        (run_id, time.time(), kind, json.dumps(data, sort_keys=True)))

    def _touch(self, run_id):
        self.db.execute("UPDATE runs SET updated = ? WHERE id = ?", (time.time(), run_id))

    def create_run(self, repo, branch, checkout, profile, profile_by, steps, origin=None,
                   mode_env=None, identity=None):
        ident = identity or {}
        run_id, now = uuid.uuid4().hex[:8], time.time()
        with self.tx():
            existing = self.find_open_run(repo, branch)
            if existing:
                raise JournalError("an open run already exists for %s %s: %s (use `own-pr adopt %s`)"
                                   % (repo, branch, existing["id"], existing["id"]))
            self.db.execute(
                "INSERT INTO runs (id, repo, branch, checkout, origin, profile, profile_by, mode_env,"
                " claude_session, codex_session, agterm_session, created, updated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, repo, branch, checkout, origin, profile, profile_by, mode_env,
                 ident.get("claude"), ident.get("codex"), ident.get("agterm"), now, now))
            for step in steps:
                self.db.execute("INSERT INTO steps (run_id, step) VALUES (?, ?)", (run_id, step))
            self._event(run_id, "start", profile=profile, profile_by=profile_by, origin=origin)
        return run_id

    def run(self, run_id):
        row = self.db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise JournalError("no run %r" % run_id)
        return dict(row)

    def find_open_run(self, repo, branch):
        row = self.db.execute("SELECT * FROM runs WHERE repo = ? AND branch = ? AND state = 'open'",
                              (repo, branch)).fetchone()
        return dict(row) if row else None

    def open_runs(self):
        rows = self.db.execute("SELECT * FROM runs WHERE state = 'open' ORDER BY updated DESC")
        return [dict(r) for r in rows]

    def update_run(self, run_id, **fields):
        for key in fields:
            if key not in UPDATABLE:
                raise JournalError("cannot update run field %r" % key)
        self.run(run_id)
        with self.tx():
            for key, value in fields.items():
                self.db.execute("UPDATE runs SET %s = ? WHERE id = ?" % key, (value, run_id))
            self._touch(run_id)
            self._event(run_id, "update", **fields)

    def steps(self, run_id):
        rows = self.db.execute("SELECT * FROM steps WHERE run_id = ?", (run_id,))
        return {r["step"]: dict(r) for r in rows}

    def ensure_steps(self, run_id, step_ids):
        with self.tx():
            have = set(self.steps(run_id))
            added = [s for s in step_ids if s not in have]
            for step in added:
                self.db.execute("INSERT INTO steps (run_id, step) VALUES (?, ?)", (run_id, step))
            if added:
                self._event(run_id, "steps-added", steps=added)
        return added

    def set_step(self, run_id, step, status, evidence=None, note=None, by=None, mode=None):
        if status not in STATUSES:
            raise JournalError("status must be one of %s, got %r" % ("|".join(STATUSES), status))
        with self.tx():
            cur = self.db.execute(
                "UPDATE steps SET status = ?, attempts = attempts + ?,"
                " evidence = CASE WHEN ? = 'pending' THEN NULL ELSE COALESCE(?, evidence) END,"
                " note = COALESCE(?, note), by = ?, updated = ? WHERE run_id = ? AND step = ?",
                (status, 1 if status == "running" else 0, status, evidence, note, by, time.time(),
                 run_id, step))
            if cur.rowcount == 0:
                raise JournalError("run %s has no step %r" % (run_id, step))
            self._touch(run_id)
            self._event(run_id, "step", step=step, status=status, evidence=evidence, note=note, by=by,
                        mode=mode)

    def add_owed(self, run_id, text, step=None):
        with self.tx():
            cur = self.db.execute("INSERT INTO owed (run_id, step, text, created) VALUES (?, ?, ?, ?)",
                                  (run_id, step, text, time.time()))
            self._touch(run_id)
            self._event(run_id, "owe", id=cur.lastrowid, step=step, text=text)
        return cur.lastrowid

    def open_owed(self, run_id=None):
        sql, args = "SELECT * FROM owed WHERE cleared IS NULL", ()
        if run_id:
            sql, args = sql + " AND run_id = ?", (run_id,)
        return [dict(r) for r in self.db.execute(sql + " ORDER BY id", args)]

    def owed(self, owed_id):
        row = self.db.execute("SELECT * FROM owed WHERE id = ?", (owed_id,)).fetchone()
        if not row:
            raise JournalError("no owed item %r" % owed_id)
        return dict(row)

    def clear_owed(self, owed_id):
        item = self.owed(owed_id)
        with self.tx():
            self.db.execute("UPDATE owed SET cleared = ? WHERE id = ?", (time.time(), owed_id))
            self._touch(item["run_id"])
            self._event(item["run_id"], "clear", id=owed_id)

    def clear_owed_for_step(self, run_id, step):
        with self.tx():
            self.db.execute("UPDATE owed SET cleared = ? WHERE run_id = ? AND step = ?"
                            " AND cleared IS NULL", (time.time(), run_id, step))
            self._event(run_id, "clear-step", step=step)

    def claim(self, env, run_id):
        with self.tx():
            row = self.db.execute("SELECT c.run_id, r.state FROM claims c"
                                  " LEFT JOIN runs r ON r.id = c.run_id WHERE c.env = ?",
                                  (env,)).fetchone()
            if row and row["run_id"] != run_id and row["state"] == "open":
                raise JournalError("%s is claimed by run %s" % (env, row["run_id"]))
            self.db.execute("INSERT OR REPLACE INTO claims (env, run_id, claimed) VALUES (?, ?, ?)",
                            (env, run_id, time.time()))
            self._event(run_id, "claim", env=env)

    def release(self, env, run_id):
        with self.tx():
            cur = self.db.execute("DELETE FROM claims WHERE env = ? AND run_id = ?", (env, run_id))
            if cur.rowcount == 0:
                raise JournalError("run %s does not hold %s" % (run_id, env))
            self._event(run_id, "release", env=env)

    def claims(self, run_id=None):
        sql, args = "SELECT * FROM claims", ()
        if run_id:
            sql, args = sql + " WHERE run_id = ?", (run_id,)
        return [dict(r) for r in self.db.execute(sql + " ORDER BY env", args)]

    def close_run(self, run_id):
        self.run(run_id)
        with self.tx():
            self.db.execute("UPDATE runs SET state = 'closed', updated = ? WHERE id = ?",
                            (time.time(), run_id))
            self.db.execute("DELETE FROM claims WHERE run_id = ?", (run_id,))
            self._event(run_id, "close")

    def export(self):
        runs = []
        for row in self.db.execute("SELECT * FROM runs ORDER BY created"):
            run = dict(row)
            run["steps"] = self.steps(run["id"])
            run["owed"] = [dict(r) for r in self.db.execute(
                "SELECT * FROM owed WHERE run_id = ? ORDER BY id", (run["id"],))]
            run["claims"] = self.claims(run["id"])
            run["events"] = [dict(r) for r in self.db.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY id", (run["id"],))]
            runs.append(run)
        return {"runs": runs}

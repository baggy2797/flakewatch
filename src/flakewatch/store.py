"""SQLite run history. One file, safe to cache/restore between CI runs."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from .models import CaseResult, RunInfo, Status

SCHEMA_VERSION = 1
_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  commit_sha TEXT,
  ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
  run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  test_id TEXT NOT NULL,
  status TEXT NOT NULL,
  duration REAL NOT NULL,
  attempts INTEGER NOT NULL,
  retried_pass INTEGER NOT NULL,
  fail_type TEXT,
  fail_message TEXT,
  fail_trace TEXT,
  framework TEXT NOT NULL,
  PRIMARY KEY (run_id, test_id)
);
CREATE INDEX IF NOT EXISTS idx_results_test ON results(test_id);
"""


class HistoryStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            self._conn.close()
            raise RuntimeError(f"{path} was written by a newer flakewatch (schema {version})")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._conn:
            yield self._conn

    def ingest(self, run: RunInfo, results: list[CaseResult]) -> None:
        """Insert a run; re-ingesting the same run_id replaces it (idempotent re-runs)."""
        with self._tx() as c:
            c.execute("DELETE FROM runs WHERE run_id = ?", (run.run_id,))
            c.execute(
                "INSERT INTO runs(run_id, commit_sha, ts) VALUES (?, ?, ?)",
                (run.run_id, run.commit_sha, run.timestamp),
            )
            c.executemany(
                "INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        run.run_id,
                        r.test_id,
                        r.status.value,
                        r.duration,
                        r.attempts,
                        int(r.retried_pass),
                        r.fail_type,
                        r.fail_message,
                        r.fail_trace,
                        r.framework,
                    )
                    for r in results
                ],
            )

    def prune(self, keep_runs: int) -> int:
        """Delete everything but the most recent `keep_runs` runs. Returns runs removed."""
        with self._tx() as c:
            cur = c.execute(
                "DELETE FROM runs WHERE run_id NOT IN "
                "(SELECT run_id FROM runs ORDER BY ts DESC, run_id DESC LIMIT ?)",
                (keep_runs,),
            )
            return cur.rowcount

    def runs(self, window: int | None = None) -> list[RunInfo]:
        """Runs in chronological order (oldest first), limited to the latest `window`."""
        rows = self._conn.execute(
            "SELECT run_id, commit_sha, ts FROM runs ORDER BY ts DESC, run_id DESC LIMIT ?",
            (window if window else -1,),
        ).fetchall()
        return [RunInfo(run_id=r[0], commit_sha=r[1], timestamp=r[2]) for r in reversed(rows)]

    def results_for(self, run_ids: list[str]) -> list[tuple[RunInfo, CaseResult]]:
        by_run = {r.run_id: r for r in self.runs()}
        out: list[tuple[RunInfo, CaseResult]] = []
        with closing(self._conn.cursor()) as cur:
            for rid in run_ids:
                for row in cur.execute("SELECT * FROM results WHERE run_id = ?", (rid,)):
                    out.append(
                        (
                            by_run[rid],
                            CaseResult(
                                test_id=row["test_id"],
                                status=Status(row["status"]),
                                duration=row["duration"],
                                attempts=row["attempts"],
                                retried_pass=bool(row["retried_pass"]),
                                fail_type=row["fail_type"],
                                fail_message=row["fail_message"],
                                fail_trace=row["fail_trace"],
                                framework=row["framework"],
                            ),
                        )
                    )
        return out

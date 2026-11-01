from __future__ import annotations

import sqlite3

import pytest

from flakewatch.models import CaseResult, RunInfo, Status
from flakewatch.signatures import normalize, signature
from flakewatch.store import HistoryStore


def test_signature_ignores_volatile_parts():
    a = signature("X", "timeout after 30s for element #id-123 at 2025-01-01T10:00:00Z", "")
    b = signature("X", "timeout after 45s for element #id-999 at 2026-02-03T11:12:13Z", "")
    c = signature("X", "something else entirely", "")
    assert a == b and a != c and len(a) == 10


def test_signature_strips_selenium_session_info_and_uuid():
    m1 = "stale element\n(Session info: chrome=118.0.1)"
    m2 = "stale element\n(Session info: chrome=119.9.9)"
    assert signature("E", m1, "") == signature("E", m2, "")
    assert "<uuid>" in normalize("id 123e4567-e89b-12d3-a456-426614174000")


def test_signature_uses_top_app_frame():
    t1 = 'File "/x/site-packages/selenium/w.py", line 5, in until\n  File "tests/a.py", line 9, in test_a'
    t2 = 'File "tests/b.py", line 9, in test_b'
    assert signature("E", "m", t1) != signature("E", "m", t2)
    java = "\tat org.openqa.selenium.X.y(X.java:1)\n\tat com.acme.Foo.bar(Foo.java:2)"
    assert signature("E", "m", java) == signature("E", "m", java.replace("2)", "99)"))


def test_signature_empty():
    assert signature(None, None, None) == signature("", "", "")


def _res(tid="a::t", status=Status.PASSED):
    return CaseResult(test_id=tid, status=status, fail_message="m", fail_type="E", fail_trace="t")


def test_store_roundtrip_and_idempotent_reingest(tmp_path):
    s = HistoryStore(tmp_path / "sub" / "h.db")
    s.ingest(RunInfo(run_id="r1", commit_sha="x", timestamp=1), [_res(), _res("b::t")])
    s.ingest(RunInfo(run_id="r1", commit_sha="x", timestamp=1), [_res("c::t")])
    rows = s.results_for(["r1"])
    assert [r.test_id for _, r in rows] == ["c::t"]
    assert rows[0][1].fail_message == "m"
    s.close()


def test_store_persists_between_opens(tmp_path):
    p = tmp_path / "h.db"
    s = HistoryStore(p)
    s.ingest(RunInfo(run_id="r1", timestamp=1), [_res()])
    s.close()
    s2 = HistoryStore(p)
    assert [r.run_id for r in s2.runs()] == ["r1"]
    s2.close()


def test_store_window_order_and_prune():
    s = HistoryStore(":memory:")
    for i in (3, 1, 2):
        s.ingest(RunInfo(run_id=f"r{i}", timestamp=i), [_res()])
    assert [r.run_id for r in s.runs()] == ["r1", "r2", "r3"]
    assert [r.run_id for r in s.runs(2)] == ["r2", "r3"]
    assert s.prune(2) == 1
    assert [r.run_id for r in s.runs()] == ["r2", "r3"]
    assert s.results_for(["r1"]) == []  # cascade
    s.close()


def test_store_rejects_newer_schema(tmp_path):
    p = tmp_path / "h.db"
    c = sqlite3.connect(p)
    c.execute("PRAGMA user_version = 99")
    c.commit()
    c.close()
    with pytest.raises(RuntimeError, match="newer flakewatch"):
        HistoryStore(p)

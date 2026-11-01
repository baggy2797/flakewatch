from __future__ import annotations

from datetime import datetime, timezone

import pytest

from flakewatch import quarantine as q
from flakewatch.analyzer import analyze
from flakewatch.models import Cause, Classification, QuarantineFile

D = lambda s: datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)  # noqa: E731


def test_add_renew_expire_cycle(golden_store, tmp_path):
    rep = analyze(golden_store)
    f = tmp_path / "q.json"
    new, ch = q.update(q.load(f), rep, ttl_days=14, now=D("2025-01-01"))
    q.save(new, f)
    assert len(ch["added"]) == len(new.entries) >= 2
    assert all(e.added == "2025-01-01" and e.expires == "2025-01-15" for e in new.entries)

    again, ch2 = q.update(q.load(f), rep, ttl_days=14, now=D("2025-01-10"))
    assert not ch2["added"] and len(ch2["renewed"]) == len(new.entries)
    assert all(e.expires == "2025-01-24" and e.renewals == 1 for e in again.entries)

    stale, ch3 = q.update(
        again, analyze(golden_store, threshold=1.01), ttl_days=14, now=D("2025-03-01")
    )
    assert len(ch3["expired"]) == len(new.entries) and not stale.entries


def test_unrenewed_entries_stay_until_ttl(golden_store):
    rep = analyze(golden_store)
    base, _ = q.update(QuarantineFile(), rep, now=D("2025-01-01"))
    empty_report = rep.model_copy(update={"tests": []})
    kept, ch = q.update(base, empty_report, now=D("2025-01-05"))
    assert len(kept.entries) == len(base.entries) and not ch["renewed"]


def test_min_score_filters(golden_store):
    rep = analyze(golden_store)
    none, _ = q.update(QuarantineFile(), rep, min_score=1.01, now=D("2025-01-01"))
    assert not none.entries


def test_category_recorded(golden_store):
    rep = analyze(golden_store)
    rep.tests[0].classification = Classification(category=Cause.DATA, confidence=0.5)
    new, _ = q.update(QuarantineFile(), rep, now=D("2025-01-01"))
    assert {e.category for e in new.entries} >= {"data"}


def test_is_active_boundary():
    e = q.QuarantineEntry(test_id="a", added="2025-01-01", expires="2025-01-15")
    assert q.is_active(e, D("2025-01-15")) and not q.is_active(e, D("2025-01-16"))


def test_load_missing_returns_empty(tmp_path):
    assert q.load(tmp_path / "nope.json").entries == []


def test_emit_formats():
    f = QuarantineFile(
        entries=[
            q.QuarantineEntry(
                test_id="tests.ui.test_login.TestLogin::test_a",
                added="2025-01-01",
                expires="2999-01-01",
            ),
            q.QuarantineEntry(
                test_id="com.acme.CartTest::addItem", added="2025-01-01", expires="2999-01-01"
            ),
            q.QuarantineEntry(test_id="old::x", added="2020-01-01", expires="2020-02-01"),
        ]
    )
    py = q.emit(f, "pytest")
    assert "--deselect=tests/ui/test_login.py::TestLogin::test_a" in py
    assert "old" not in py
    assert (
        q.emit(f, "surefire") == "!tests.ui.test_login.TestLogin#test_a,!com.acme.CartTest#addItem"
    )
    assert q.emit(f, "ids").count("\n") == 1
    with pytest.raises(ValueError):
        q.emit(f, "nope")

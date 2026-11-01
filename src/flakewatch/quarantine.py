"""Quarantine file with TTL. Entries expire so quarantined tests cannot be forgotten."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import QuarantineEntry, QuarantineFile, Report

DATE_FMT = "%Y-%m-%d"


def _today(now: datetime | None) -> datetime:
    return now or datetime.now(tz=timezone.utc)


def load(path: Path) -> QuarantineFile:
    if not path.exists():
        return QuarantineFile()
    return QuarantineFile.model_validate_json(path.read_text(encoding="utf-8"))


def save(q: QuarantineFile, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    q.entries.sort(key=lambda e: e.test_id)
    path.write_text(q.model_dump_json(indent=2) + "\n", encoding="utf-8")


def is_active(entry: QuarantineEntry, now: datetime | None = None) -> bool:
    return entry.expires >= _today(now).strftime(DATE_FMT)


def update(
    q: QuarantineFile,
    report: Report,
    ttl_days: int = 14,
    min_score: float = 0.3,
    now: datetime | None = None,
) -> tuple[QuarantineFile, dict[str, list[str]]]:
    """Add/renew entries for flaky tests >= min_score and drop expired ones.

    Returns the new file plus {"added": [...], "renewed": [...], "expired": [...]}.
    A test that stopped being flaky is NOT renewed, so it falls out when its TTL ends.
    """
    today = _today(now)
    today_s = today.strftime(DATE_FMT)
    expires = (today + timedelta(days=ttl_days)).strftime(DATE_FMT)
    kept: dict[str, QuarantineEntry] = {}
    changes: dict[str, list[str]] = {"added": [], "renewed": [], "expired": []}
    for e in q.entries:
        if is_active(e, today):
            kept[e.test_id] = e
        else:
            changes["expired"].append(e.test_id)
    for t in report.tests:
        if t.metrics.verdict != "flaky" or t.metrics.score < min_score:
            continue
        cat = t.classification.category.value if t.classification else "unknown"
        reason = f"score {t.metrics.score:.2f}, flip rate {t.metrics.flip_rate:.2f}"
        if t.test_id in kept:
            e = kept[t.test_id]
            e.expires, e.reason, e.category = expires, reason, cat
            e.score, e.renewals = t.metrics.score, e.renewals + 1
            changes["renewed"].append(t.test_id)
        else:
            kept[t.test_id] = QuarantineEntry(
                test_id=t.test_id,
                added=today_s,
                expires=expires,
                reason=reason,
                category=cat,
                score=t.metrics.score,
            )
            changes["added"].append(t.test_id)
    for k in changes:
        changes[k].sort()
    return QuarantineFile(entries=sorted(kept.values(), key=lambda e: e.test_id)), changes


def emit(q: QuarantineFile, fmt: str, now: datetime | None = None) -> str:
    """Render active entries for a test runner. Ids are `classname::name` as ingested."""
    active = [e.test_id for e in q.entries if is_active(e, now)]
    if fmt == "pytest":
        return "\n".join(f"--deselect={_pytest_node(i)}" for i in active)
    if fmt == "surefire":
        # -Dtest='!Class#method,!Class2#method2'
        parts = []
        for i in active:
            cls, _, name = i.partition("::")
            parts.append(f"!{cls}#{name}")
        return ",".join(parts)
    if fmt == "ids":
        return "\n".join(active)
    raise ValueError(f"unknown format {fmt!r}")


def _pytest_node(test_id: str) -> str:
    """`pkg.mod.Class::test` -> `pkg/mod.py::Class::test` (best effort; see README)."""
    cls, _, name = test_id.partition("::")
    parts = cls.split(".")
    idx = next((n for n, p in enumerate(parts) if p[:1].isupper()), len(parts))
    path = "/".join(parts[:idx]) + ".py"
    klass = "::".join(parts[idx:])
    return "::".join(x for x in (path, klass, name) if x)

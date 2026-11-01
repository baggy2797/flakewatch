"""Golden-file tests for report output. Regenerate with: UPDATE_GOLDEN=1 pytest tests/test_golden.py"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from flakewatch import quarantine as q
from flakewatch.analyzer import analyze
from flakewatch.cli import Engine, classify_report
from flakewatch.models import QuarantineFile
from flakewatch.report import render_markdown, to_json

GOLDEN = Path(__file__).parent / "golden"


@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1735689600")


def check(name: str, actual: str) -> None:
    path = GOLDEN / name
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(actual, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == actual, f"{name} differs; run UPDATE_GOLDEN=1"


def test_markdown_heuristic_with_quarantine(golden_store):
    rep = classify_report(analyze(golden_store), Engine.heuristic)
    qf, _ = q.update(QuarantineFile(), rep, now=datetime(2025, 1, 1, tzinfo=timezone.utc))
    check("report_heuristic.md", render_markdown(rep, qf))


def test_markdown_unclassified(golden_store):
    check("report_unclassified.md", render_markdown(analyze(golden_store)))


def test_json_mock_llm(golden_store):
    check("report_mock_llm.json", to_json(classify_report(analyze(golden_store), Engine.mock_llm)))


def test_markdown_no_flaky(golden_store):
    rep = analyze(golden_store, threshold=1.01)
    rep.tests = [t for t in rep.tests if t.metrics.verdict != "flaky"][:0]
    check("report_clean.md", render_markdown(rep))


def test_markdown_truncates_long_tables(golden_store):
    rep = analyze(golden_store)
    base = rep.tests[0]
    rep.tests = [base.model_copy(update={"test_id": f"t{i:02d}"}) for i in range(30)]
    md = render_markdown(rep)
    assert "…and 5 more" in md and "t24" in md and "t25" not in md.split("### Details")[0]

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

import pytest

from flakewatch.models import CaseResult, RunInfo, Status
from flakewatch.store import HistoryStore


def case_xml(
    classname: str,
    name: str,
    fail: tuple[str, str, str] | None = None,
    flaky: list[tuple[str, str, str]] | None = None,
    rerun_fail: list[tuple[str, str, str]] | None = None,
    skipped: bool = False,
    tag: str = "failure",
) -> str:
    out = f'<testcase classname={quoteattr(classname)} name={quoteattr(name)} time="0.5">'
    if skipped:
        out += "<skipped/>"
    if fail:
        t, m, tr = fail
        out += f"<{tag} type={quoteattr(t)} message={quoteattr(m)}>{escape(tr)}</{tag}>"
    for t, m, tr in flaky or []:
        out += (
            f"<flakyFailure type={quoteattr(t)} message={quoteattr(m)}>{escape(tr)}</flakyFailure>"
        )
    for t, m, tr in rerun_fail or []:
        out += (
            f"<rerunFailure type={quoteattr(t)} message={quoteattr(m)}>{escape(tr)}</rerunFailure>"
        )
    return out + "</testcase>"


def suite_xml(
    cases: list[str], name: str = "pytest", ts: str | None = None, props: bool = False
) -> str:
    stamp = f' timestamp="{ts}"' if ts else ""
    p = '<properties><property name="java.version" value="17"/></properties>' if props else ""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<testsuites><testsuite name="{name}" tests="{len(cases)}"{stamp}>{p}{"".join(cases)}'
        "</testsuite></testsuites>"
    )


@pytest.fixture
def write_xml(tmp_path: Path):
    def _write(name: str, xml: str) -> Path:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(xml, encoding="utf-8")
        return p

    return _write


STALE = (
    "org.openqa.selenium.StaleElementReferenceException",
    "stale element reference: element is not attached to the page document",
    "org.openqa.selenium.StaleElementReferenceException: stale element reference\n"
    "\tat com.acme.pages.Grid.rowText(Grid.java:41)",
)
TIMEOUT = (
    "org.openqa.selenium.TimeoutException",
    "Expected condition failed: waiting for visibility of element located by By.id: go",
    "org.openqa.selenium.TimeoutException: Expected condition failed\n\tat com.acme.CartTest.addItem(CartTest.java:12)",
)
CONN = (
    "requests.exceptions.ConnectionError",
    "HTTPConnectionPool(host='api', port=8080): Max retries exceeded (Connection refused)",
    'Traceback (most recent call last):\n  File "tests/api/test_orders.py", line 9, in test_create\nrequests.exceptions.ConnectionError',
)
BROKEN = ("AssertionError", "assert 500 == 200", "AssertionError: assert 500 == 200")


def golden_runs() -> list[tuple[RunInfo, str]]:
    """Five deterministic runs (commit a,a,b,c,d) covering flaky, broken and stable tests."""
    plan: list[dict[str, Any]] = [
        dict(stale=True, timeout="retry", conn=False, broken=False),
        dict(stale=False, timeout=None, conn=True, broken=False),
        dict(stale=True, timeout="retry", conn=False, broken=True),
        dict(stale=False, timeout=None, conn=False, broken=True),
        dict(stale=True, timeout=None, conn=True, broken=True),
    ]
    commits = ["a" * 40, "a" * 40, "b" * 40, "c" * 40, "d" * 40]
    out = []
    for i, p in enumerate(plan):
        cases = [
            case_xml("tests.ui.test_grid", "test_row_text", STALE if p["stale"] else None),
            case_xml("com.acme.CartTest", "addItem", flaky=[TIMEOUT] if p["timeout"] else None),
            case_xml("tests.api.test_orders", "test_create", CONN if p["conn"] else None),
            case_xml("tests.test_health", "test_ok"),
            case_xml("tests.test_checkout", "test_total", BROKEN if p["broken"] else None),
        ]
        out.append(
            (
                RunInfo(
                    run_id=f"r{i + 1}", commit_sha=commits[i], timestamp=1_700_000_000 + i * 3600
                ),
                suite_xml(cases),
            )
        )
    return out


@pytest.fixture
def golden_store(tmp_path: Path):
    from flakewatch.parser import parse_junit

    store = HistoryStore(tmp_path / "h.db")
    for run, xml in golden_runs():
        f = tmp_path / f"{run.run_id}.xml"
        f.write_text(xml, encoding="utf-8")
        results, _ = parse_junit(f)
        store.ingest(run, results)
    yield store
    store.close()


def mk_result(test_id: str, status: Status, retried: bool = False) -> CaseResult:
    return CaseResult(test_id=test_id, status=status, retried_pass=retried)

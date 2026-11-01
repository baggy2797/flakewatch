"""JUnit XML parsing for pytest, TestNG/Surefire and jest-junit output."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as ET

from .models import CaseResult, Status

_FAIL_TAGS = {"failure", "error"}
_RERUN_TAGS = {"flakyFailure", "flakyError", "rerunFailure", "rerunError"}
MAX_TRACE_CHARS = 4000
MAX_MESSAGE_CHARS = 1000


def _detect_framework(suite: Any) -> str:
    name = (suite.get("name") or "").lower()
    if name.startswith("pytest"):
        return "pytest"
    if "jest" in name:
        return "jest"
    if suite.find("properties") is not None and any(
        (p.get("name") or "").startswith(("java.", "maven", "surefire", "sun.java"))
        for p in suite.iter("property")
    ):
        return "surefire"
    if name.startswith(("com.", "org.", "io.")) or "testng" in name:
        return "surefire"
    return "unknown"


def _parse_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _evidence(el: Any) -> tuple[str, str, str]:
    exc_type = (el.get("type") or "").strip()
    message = (el.get("message") or "").strip()
    trace = (el.text or "").strip()
    if not message and trace:
        message = trace.splitlines()[0]
    if not exc_type and message:
        head = message.split(":", 1)[0].strip()
        if head and " " not in head:
            exc_type = head
    return exc_type, message[:MAX_MESSAGE_CHARS], trace[:MAX_TRACE_CHARS]


def merge_attempts(results: list[CaseResult]) -> list[CaseResult]:
    """Merge duplicate test ids (rerun plugins, sharded jobs) into one final result."""
    grouped: dict[str, list[CaseResult]] = {}
    for r in results:
        grouped.setdefault(r.test_id, []).append(r)
    merged: list[CaseResult] = []
    for test_id, items in grouped.items():
        if len(items) == 1:
            merged.append(items[0])
            continue
        final = items[-1]
        any_failed = any(i.status == Status.FAILED or i.fail_message for i in items)
        first_fail = next((i for i in items if i.fail_message or i.fail_type), None)
        retried = any(i.retried_pass for i in items) or (
            final.status == Status.PASSED and any_failed
        )
        merged.append(
            CaseResult(
                test_id=test_id,
                status=final.status,
                duration=sum(i.duration for i in items),
                attempts=sum(i.attempts for i in items),
                retried_pass=retried and final.status == Status.PASSED,
                fail_type=first_fail.fail_type if first_fail else None,
                fail_message=first_fail.fail_message if first_fail else None,
                fail_trace=first_fail.fail_trace if first_fail else None,
                framework=final.framework,
            )
        )
    return merged


def parse_junit(path: Path) -> tuple[list[CaseResult], float | None]:
    """Parse one JUnit XML file. Returns (merged results, earliest suite timestamp)."""
    root = ET.parse(str(path)).getroot()
    if root is None:
        raise ValueError(f"{path}: empty XML document")
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    out: list[CaseResult] = []
    stamps: list[float] = []
    for suite in suites:
        framework = _detect_framework(suite)
        ts = _parse_ts(suite.get("timestamp"))
        if ts is not None:
            stamps.append(ts)
        for case in suite.findall("testcase"):
            classname = (case.get("classname") or "").strip()
            name = (case.get("name") or "").strip()
            if not name:
                continue
            test_id = f"{classname}::{name}" if classname else name
            try:
                duration = float(case.get("time") or 0.0)
            except ValueError:
                duration = 0.0
            fails = [c for c in case if c.tag in _FAIL_TAGS]
            reruns = [c for c in case if c.tag in _RERUN_TAGS]
            skipped = case.find("skipped") is not None
            if fails:
                status = Status.FAILED
            elif skipped:
                status = Status.SKIPPED
            else:
                status = Status.PASSED
            first = next((c for c in case if c.tag in _FAIL_TAGS | _RERUN_TAGS), None)
            exc_type = message = trace = None
            if first is not None:
                exc_type, message, trace = _evidence(first)
            out.append(
                CaseResult(
                    test_id=test_id,
                    status=status,
                    duration=duration,
                    attempts=1 + len(reruns),
                    retried_pass=status == Status.PASSED and bool(reruns),
                    fail_type=exc_type or None,
                    fail_message=message,
                    fail_trace=trace,
                    framework=framework,
                )
            )
    return merge_attempts(out), (min(stamps) if stamps else None)

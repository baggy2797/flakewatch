from __future__ import annotations

import pytest

from flakewatch.models import Status
from flakewatch.parser import merge_attempts, parse_junit

from .conftest import STALE, TIMEOUT, case_xml, suite_xml


def test_pytest_style(write_xml):
    xml = suite_xml(
        [
            case_xml("tests.test_a", "test_ok"),
            case_xml(
                "tests.test_a", "test_bad", ("", "AssertionError: assert 1 == 2", "trace here")
            ),
            case_xml("tests.test_a", "test_skip", skipped=True),
            case_xml("tests.test_a", "test_err", ("RuntimeError", "boom", "tb"), tag="error"),
        ],
        ts="2025-01-01T10:00:00",
    )
    results, ts = parse_junit(write_xml("p.xml", xml))
    by = {r.test_id: r for r in results}
    assert by["tests.test_a::test_ok"].status == Status.PASSED
    assert by["tests.test_a::test_bad"].status == Status.FAILED
    assert by["tests.test_a::test_bad"].fail_type == "AssertionError"
    assert by["tests.test_a::test_skip"].status == Status.SKIPPED
    assert by["tests.test_a::test_err"].status == Status.FAILED
    assert by["tests.test_a::test_err"].fail_type == "RuntimeError"
    assert by["tests.test_a::test_ok"].framework == "pytest"
    assert ts == 1735725600.0


def test_surefire_flaky_failure_means_retried_pass(write_xml):
    xml = suite_xml(
        [case_xml("com.acme.CartTest", "addItem", flaky=[TIMEOUT, STALE])],
        name="com.acme.CartTest",
        props=True,
    )
    (r,), _ = parse_junit(write_xml("s.xml", xml))
    assert r.status == Status.PASSED
    assert r.retried_pass and r.attempts == 3
    assert r.fail_type == "org.openqa.selenium.TimeoutException"
    assert r.framework == "surefire"


def test_surefire_rerun_failure_stays_failed(write_xml):
    xml = suite_xml([case_xml("a.B", "t", fail=TIMEOUT, rerun_fail=[TIMEOUT])], name="a.B")
    (r,), _ = parse_junit(write_xml("s.xml", xml))
    assert r.status == Status.FAILED and not r.retried_pass and r.attempts == 2


def test_jest_style_without_attributes(write_xml):
    xml = (
        '<testsuites><testsuite name="jest tests"><testcase classname="Cart page" '
        'name="Cart page totals" time="1"><failure>Error: Execution context was destroyed\n'
        "    at foo</failure></testcase></testsuite></testsuites>"
    )
    (r,), _ = parse_junit(write_xml("j.xml", xml))
    assert r.framework == "jest"
    assert r.fail_type == "Error"
    assert r.fail_message == "Error: Execution context was destroyed"


def test_bare_testsuite_root_and_missing_name_skipped(write_xml):
    xml = '<testsuite name="pytest"><testcase classname="x" name=""/><testcase name="t" time="bad"/></testsuite>'
    results, ts = parse_junit(write_xml("b.xml", xml))
    assert [r.test_id for r in results] == ["t"]
    assert results[0].duration == 0.0 and ts is None


def test_duplicate_entries_merge_as_retry_pass(write_xml):
    xml = suite_xml([case_xml("t", "a", fail=STALE), case_xml("t", "a")])
    (r,), _ = parse_junit(write_xml("d.xml", xml))
    assert r.status == Status.PASSED and r.retried_pass and r.attempts == 2
    assert r.fail_type == STALE[0]


def test_merge_attempts_all_fail_and_single():
    from flakewatch.models import CaseResult

    a = CaseResult(test_id="x", status=Status.FAILED, fail_message="m")
    b = CaseResult(test_id="x", status=Status.FAILED, fail_message="m2")
    c = CaseResult(test_id="y", status=Status.PASSED)
    out = {r.test_id: r for r in merge_attempts([a, b, c])}
    assert out["x"].status == Status.FAILED and not out["x"].retried_pass
    assert out["y"].attempts == 1


def test_bad_timestamp_and_naive_tz(write_xml):
    xml = '<testsuite name="pytest" timestamp="not-a-date"><testcase name="t"/></testsuite>'
    _, ts = parse_junit(write_xml("t.xml", xml))
    assert ts is None


def test_xml_entity_bomb_rejected(write_xml):
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        '<testsuite name="pytest"><testcase name="&b;"/></testsuite>'
    )
    with pytest.raises(Exception):  # noqa: B017 - defusedxml EntitiesForbidden
        parse_junit(write_xml("bomb.xml", bomb))

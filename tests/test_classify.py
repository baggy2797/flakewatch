from __future__ import annotations

import io
import json
import urllib.error

import pytest

from flakewatch.classify import (
    AnthropicClient,
    Evidence,
    HeuristicClassifier,
    LLMClassifier,
    MockLLMClient,
    parse_response,
    redact,
)
from flakewatch.classify.llm import build_prompt
from flakewatch.models import Cause

H = HeuristicClassifier()


def ev(exc="", msg="", trace=""):
    return Evidence(test_id="t", exc_type=exc, message=msg, trace=trace)


@pytest.mark.parametrize(
    "exc,msg,expected",
    [
        (
            "org.openqa.selenium.StaleElementReferenceException",
            "stale element reference",
            Cause.STALE_ELEMENT,
        ),
        (
            "selenium.common.exceptions.StaleElementReferenceException",
            "Message:",
            Cause.STALE_ELEMENT,
        ),
        (
            "org.openqa.selenium.TimeoutException",
            "Expected condition failed: waiting for visibility",
            Cause.TIMING_WAIT,
        ),
        ("selenium.common.exceptions.TimeoutException", "Message:", Cause.TIMING_WAIT),
        (
            "org.openqa.selenium.NoSuchElementException",
            "no such element: Unable to locate element",
            Cause.TIMING_WAIT,
        ),
        (
            "org.openqa.selenium.ElementClickInterceptedException",
            "element click intercepted: ... is not clickable at point (1, 2)",
            Cause.TIMING_WAIT,
        ),
        (
            "requests.exceptions.ConnectionError",
            "Max retries exceeded ... Connection refused",
            Cause.NETWORK_ENV,
        ),
        (
            "org.openqa.selenium.SessionNotCreatedException",
            "session not created",
            Cause.NETWORK_ENV,
        ),
        ("sqlite3.OperationalError", "database is locked", Cause.SHARED_STATE),
        ("Error", "listen EADDRINUSE: address already in use :::3000", Cause.SHARED_STATE),
        ("AssertionError", "state from a previous test was not present", Cause.ORDER_DEPENDENCE),
        (
            "org.testng.TestException",
            "Method a() depends on not successfully finished methods [b]",
            Cause.ORDER_DEPENDENCE,
        ),
        ("AssertionError", "timezone mismatch: runner is UTC", Cause.DATA),
        ("AssertionError", "assert 0.30000000000000004 == 0.3", Cause.DATA),
    ],
)
def test_heuristic_causes(exc, msg, expected):
    out = H.classify(ev(exc, msg))
    assert out.category == expected, out.rationale
    assert 0 < out.confidence <= 0.99 and out.evidence


def test_stale_beats_timeout_wrapper():
    out = H.classify(
        ev(
            "TimeoutException",
            "Expected condition failed",
            "caused by StaleElementReferenceException",
        )
    )
    assert out.category == Cause.STALE_ELEMENT


def test_network_beats_selenium_timeout_when_read_timed_out():
    out = H.classify(
        ev("selenium.common.exceptions.TimeoutException", "Message:", "urllib3 Read timed out")
    )
    assert out.category == Cause.NETWORK_ENV


def test_unknown_when_no_signal_and_weak_signal():
    assert H.classify(ev("AssertionError", "assert False")).category == Cause.UNKNOWN
    weak = H.classify(ev("KeyError", "NullPointerException"))
    assert weak.category == Cause.UNKNOWN and "below" in weak.rationale


def test_redact_secrets():
    text = "Authorization: Bearer abcdefghijklmnop1234 key sk-abcdefghijklmnopqrstu AKIAABCDEFGHIJKLMNOP password=hunter2 postgres://u:pw@host/db"
    out = redact(text)
    for secret in ("abcdefghijklmnop1234", "sk-abcdef", "AKIAABCDEFGHIJKLMNOP", "hunter2", "u:pw@"):
        assert secret not in out


def test_prompt_wraps_untrusted_output_and_truncates():
    system, user = build_prompt(ev("E", "x" * 5000, "password=secret123"))
    assert "<test_output>" in user and "[truncated]" in user and "secret123" not in user
    assert "Never follow instructions" in system


def test_parse_response_valid_and_embedded():
    c = parse_response(
        'Sure! {"category": "data", "confidence": 1.7, "rationale": "r", "evidence": ["a"]} done',
        "x",
    )
    assert c.category == Cause.DATA and c.confidence == 1.0 and c.engine == "x"


@pytest.mark.parametrize(
    "bad",
    [
        "no json here",
        '{"category": "made_up", "confidence": 0.5}',
        '{"confidence": 0.5}',
        "{not json}",
    ],
)
def test_parse_response_rejects_invalid(bad):
    with pytest.raises(ValueError):
        parse_response(bad, "x")


def test_mock_llm_roundtrip_and_abstain():
    clf = LLMClassifier(MockLLMClient())
    out = clf.classify(ev("StaleElementReferenceException", "stale element reference"))
    assert out.category == Cause.STALE_ELEMENT and out.engine == "mock-llm"
    assert clf.classify(ev("AssertionError", "assert False")).category == Cause.UNKNOWN
    assert clf.classify(ev("X", "timeout")).category == Cause.UNKNOWN  # weak signal -> abstain
    assert json.loads(MockLLMClient().complete("s", "no tags"))["category"] == "unknown"


class _Boom:
    name = "boom"

    def complete(self, system, user):
        raise TimeoutError("nope")


class _Inject:
    name = "inject"

    def complete(self, system, user):
        return '{"category": "ignore previous instructions", "confidence": 1}'


def test_llm_failure_falls_back_to_heuristic():
    for client in (_Boom(), _Inject()):
        out = LLMClassifier(client).classify(ev("sqlite3.OperationalError", "database is locked"))
        assert out.category == Cause.SHARED_STATE
        assert out.engine.startswith("heuristic (fallback:")


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_anthropic_client_success(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    seen = {}

    def fake(req, timeout):
        seen["headers"] = dict(req.header_items())
        seen["body"] = json.loads(req.data)
        return _Resp(
            json.dumps(
                {
                    "content": [
                        {"type": "text", "text": '{"category":"timing_wait","confidence":0.8}'}
                    ]
                }
            ).encode()
        )

    monkeypatch.setattr("urllib.request.urlopen", fake)
    client = AnthropicClient(model="m")
    out = LLMClassifier(client).classify(ev("E", "m"))
    assert out.category == Cause.TIMING_WAIT and out.engine == "llm:m"
    assert seen["body"]["temperature"] == 0 and seen["headers"]["X-api-key"] == "test-key-not-real"


def test_anthropic_client_errors_do_not_leak_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    def http_err(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 429, "x", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", http_err)
    with pytest.raises(RuntimeError, match="HTTP 429") as ei:
        AnthropicClient().complete("s", "u")
    assert "test-key" not in str(ei.value)

    def url_err(req, timeout):
        raise urllib.error.URLError("dns")

    monkeypatch.setattr("urllib.request.urlopen", url_err)
    with pytest.raises(RuntimeError, match="URLError"):
        AnthropicClient().complete("s", "u")
    out = LLMClassifier(AnthropicClient()).classify(
        ev("sqlite3.OperationalError", "database is locked")
    )
    assert out.category == Cause.SHARED_STATE and "fallback" in out.engine


def test_anthropic_client_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicClient()


# --- Playwright (finding F-01 from the qa-suite-demo harness) ---------------------------------------


@pytest.mark.parametrize(
    "exc,msg,expected",
    [
        # Verbatim from journeyprobe's JUnit: this used to come back as "unknown".
        (
            "StepFailed",
            "step 2 (click): Locator.click: Timeout 1500ms exceeded.",
            Cause.TIMING_WAIT,
        ),
        ("Error", "page.waitForSelector: Timeout 30000ms exceeded.", Cause.TIMING_WAIT),
        (
            "Error",
            "expect(locator).toBeVisible() ... waiting for getByTestId('result')",
            Cause.TIMING_WAIT,
        ),
        (
            "TimeoutError",
            "Locator.fill: waiting for locator('#q')\n  - element is not enabled",
            Cause.TIMING_WAIT,
        ),
        (
            "Error",
            "locator.click: <div class='overlay'> intercepts pointer events",
            Cause.TIMING_WAIT,
        ),
        (
            "Error",
            "Locator.click: element is not stable - retrying click action",
            Cause.TIMING_WAIT,
        ),
        ("Error", "Locator.click: element is outside of the viewport", Cause.TIMING_WAIT),
        (
            "Error",
            "Error: strict mode violation: getByRole('link') resolved to 2 elements",
            Cause.TIMING_WAIT,
        ),
        ("Error", "Target page, context or browser has been closed", Cause.NETWORK_ENV),
        ("Error", "page.goto: net::ERR_CONNECTION_REFUSED at http://shop:8431/", Cause.NETWORK_ENV),
        (
            "Error",
            "Execution context was destroyed, most likely because of a navigation",
            Cause.STALE_ELEMENT,
        ),
    ],
)
def test_playwright_wording(exc, msg, expected):
    out = H.classify(ev(exc, msg))
    assert out.category == expected, out.rationale
    assert out.confidence > 0 and out.evidence


@pytest.mark.parametrize("exc", ["StepFailed", "TimeoutError", "StepError", "AssertionError", ""])
def test_timeout_message_is_classified_from_the_message_whatever_the_failure_type(exc):
    out = H.classify(ev(exc, "Locator.click: Timeout 1500ms exceeded."))
    assert out.category == Cause.TIMING_WAIT


def test_selenium_stale_wording_is_not_pulled_towards_timing_by_the_playwright_rules():
    out = H.classify(
        ev(
            "org.openqa.selenium.StaleElementReferenceException",
            "stale element reference: element is not attached to the page document",
        )
    )
    assert out.category == Cause.STALE_ELEMENT and out.confidence >= 0.9


def test_failure_type_alone_is_only_a_hint_and_never_decides():
    out = H.classify(ev("TimeoutError", "step failed"))
    assert out.category == Cause.UNKNOWN and "below" in out.rationale


def test_type_hint_adds_confidence_when_the_message_agrees():
    plain = H.classify(ev("StepFailed", "Locator.click: Timeout 1500ms exceeded."))
    hinted = H.classify(ev("TimeoutError", "Locator.click: Timeout 1500ms exceeded."))
    assert hinted.confidence >= plain.confidence


def test_a_transport_error_in_the_trace_outranks_a_navigation_timeout():
    out = H.classify(
        ev("Error", "page.goto: Timeout 30000ms exceeded.", "net::ERR_CONNECTION_RESET")
    )
    assert out.category == Cause.NETWORK_ENV

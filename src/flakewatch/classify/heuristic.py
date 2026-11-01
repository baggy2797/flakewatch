"""Deterministic, explainable root-cause rules. Selenium-aware first.

Each rule contributes a weight to one cause; weights for a cause combine as a noisy-OR
(1 - prod(1 - w)). The top cause wins if it clears MIN_SCORE, otherwise "unknown".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Cause, Classification
from .base import Evidence

MIN_SCORE = 0.35


@dataclass(frozen=True)
class Rule:
    cause: Cause
    pattern: re.Pattern[str]
    weight: float
    label: str


def _r(cause: Cause, pat: str, weight: float, label: str) -> Rule:
    return Rule(cause, re.compile(pat, re.I | re.S), weight, label)


C = Cause
# fmt: off
RULES: list[Rule] = [
    # --- Selenium / browser-automation specifics ---------------------------------------------
    _r(C.STALE_ELEMENT, r"StaleElementReference", 0.97, "StaleElementReferenceException"),
    _r(C.STALE_ELEMENT, r"stale element", 0.95, "'stale element' message"),
    _r(C.STALE_ELEMENT, r"not attached to the page document", 0.9, "element detached from page"),
    _r(C.STALE_ELEMENT, r"detached from (the )?dom|element is detached", 0.85, "detached from DOM"),
    _r(C.STALE_ELEMENT, r"Execution context was destroyed|Node is detached|frame was detached", 0.8,
       "puppeteer/playwright detached context"),
    _r(C.TIMING_WAIT, r"ElementClickIntercepted|element click intercepted", 0.85,
       "ElementClickInterceptedException (overlay/animation not settled)"),
    _r(C.TIMING_WAIT, r"is not clickable at point|Other element would receive the click", 0.85,
       "click target obscured"),
    _r(C.TIMING_WAIT, r"ElementNotInteractable|element not interactable", 0.7,
       "element not interactable yet"),
    _r(C.TIMING_WAIT, r"NoSuchElement|no such element|Unable to locate element", 0.65,
       "element not found (not rendered yet?)"),
    _r(C.TIMING_WAIT, r"\bTimeoutException\b", 0.6, "Selenium TimeoutException"),
    _r(C.TIMING_WAIT, r"Expected condition failed|waiting for (visibility|presence|element|selector)",
       0.7, "explicit wait expired"),
    _r(C.TIMING_WAIT, r"WebDriverWait|\.until\(", 0.3, "WebDriverWait in stack"),
    _r(C.TIMING_WAIT, r"Timeout of \d+ ?ms exceeded|Exceeded timeout of \d+ ?ms|"
       r"Timeout - Async callback was not invoked", 0.6, "test/async timeout"),
    _r(C.TIMING_WAIT, r"waitFor|waiting for .* to (be|become)", 0.35, "waitFor/wait phrasing"),
    _r(C.TIMING_WAIT, r"race condition|not yet (rendered|loaded|visible)|still (loading|pending)",
       0.5, "explicit race/loading wording"),
    _r(C.TIMING_WAIT, r"(expected|but was|got|assert).{0,40}(loading|spinner|pending|in progress)", 0.5,
       "assertion saw a transient UI state"),
    # --- Network / environment ----------------------------------------------------------------
    _r(C.NETWORK_ENV, r"ECONNREFUSED|ECONNRESET|ETIMEDOUT|EAI_AGAIN|ENOTFOUND", 0.9,
       "socket-level error code"),
    _r(C.NETWORK_ENV, r"Connection (refused|reset|aborted)|ConnectionError|ConnectionResetError",
       0.9, "connection error"),
    _r(C.NETWORK_ENV, r"UnknownHostException|Name or service not known|getaddrinfo|"
       r"Temporary failure in name resolution", 0.9, "DNS failure"),
    _r(C.NETWORK_ENV, r"SocketTimeout|Read timed out|ReadTimeout|HTTPConnectionPool|"
       r"Max retries exceeded|Remote end closed", 0.88, "HTTP/socket timeout"),
    _r(C.NETWORK_ENV, r"Bad Gateway|Service Unavailable|Gateway Time-?out", 0.85, "upstream 5xx"),
    _r(C.NETWORK_ENV, r"SSLError|SSLHandshake|CERTIFICATE_VERIFY_FAILED", 0.8, "TLS error"),
    _r(C.NETWORK_ENV, r"No space left on device|Too many open files|Cannot allocate memory|"
       r"OutOfMemoryError|ENOMEM|disk quota", 0.85, "resource exhaustion on runner"),
    _r(C.NETWORK_ENV, r"SessionNotCreated|chrome not reachable|disconnected: not connected to "
       r"DevTools|session deleted because of page crash|tab crashed|Target closed|"
       r"browser has disconnected", 0.88, "browser/driver session died"),
    _r(C.NETWORK_ENV, r"net::ERR_\w+|status code 5\d\d|HTTP (error )?5\d\d", 0.8,
       "browser/HTTP transport error"),
    _r(C.NETWORK_ENV, r"rate limit|429 Too Many Requests|quota exceeded", 0.7, "rate limited"),
    # --- Shared state -------------------------------------------------------------------------
    _r(C.SHARED_STATE, r"ConcurrentModification|database is locked|deadlock|lock wait timeout",
       0.85, "concurrent access to shared resource"),
    _r(C.SHARED_STATE, r"Address already in use|EADDRINUSE|port \d+ is already", 0.8,
       "port already in use (leaked server)"),
    _r(C.SHARED_STATE, r"being used by another process|resource busy|Text file busy|"
       r"file (is )?locked", 0.8, "file held by another process"),
    _r(C.SHARED_STATE, r"singleton|global state|static (field|variable)|shared (state|instance|"
       r"fixture|session|cache|database|db)|leaked|left over|leftover|pollut", 0.7,
       "shared-state vocabulary"),
    _r(C.SHARED_STATE, r"cache (hit|miss|entry|contains)|stale cache|cached value", 0.5,
       "cache interaction"),
    _r(C.SHARED_STATE, r"(already exists|duplicate (key|entry)|UNIQUE constraint|IntegrityError)",
       0.4, "uniqueness violation (row left by someone else)"),
    # --- Order dependence ---------------------------------------------------------------------
    _r(C.ORDER_DEPENDENCE, r"depends? on(Methods|Groups)?|did not run before|must run (after|"
       r"before)|only passes? (in|when) .{0,30}(order|sequence|isolation)|in isolation|"
       r"test order|execution order|run order", 0.8, "explicit order wording"),
    _r(C.ORDER_DEPENDENCE, r"skipped because of configuration failure|"
       r"depends on not successfully finished methods", 0.9, "TestNG dependency not satisfied"),
    _r(C.ORDER_DEPENDENCE, r"previous test|earlier test|prior test|preceding test", 0.7,
       "refers to another test"),
    _r(C.ORDER_DEPENDENCE, r"randomly-seed|pytest-randomly|random[_-]order|--shuffle|"
       r"randomize", 0.6, "randomised order in play"),
    _r(C.ORDER_DEPENDENCE, r"fixture '?\w+'? (not found|was not|has not)|not (been )?"
       r"(initialized|initialised|set up|setup)|uninitiali[sz]ed|before(All|Each|Class)? .{0,20}"
       r"(not|never)", 0.55, "setup that never ran / is missing"),
    _r(C.ORDER_DEPENDENCE, r"KeyError: '(user|session|token|current|last|id)\w*'|"
       r"AttributeError: 'NoneType'|NullPointerException", 0.3, "missing state from elsewhere"),
    _r(C.ORDER_DEPENDENCE, r"No such table|relation \"\w+\" does not exist|table .* doesn't exist",
       0.4, "schema/state not prepared"),
    # --- Test data ----------------------------------------------------------------------------
    _r(C.DATA, r"timezone|time zone|\bDST\b|daylight|off by one day|midnight|leap", 0.75,
       "time/timezone-dependent data"),
    _r(C.DATA, r"locale|decimal separator|\bcurrency\b|encoding|UnicodeDecode|charset", 0.6,
       "locale/encoding-dependent data"),
    _r(C.DATA, r"not (almost )?equal.{0,40}(delta|places|tolerance)|within \d|floating|"
       r"precision|rounding", 0.7, "numeric precision"),
    _r(C.DATA, r"random|\bseed\b|faker|generated|uuid|nondeterministic|non-deterministic", 0.55,
       "random/generated test data"),
    _r(C.DATA, r"(order|ordering|sorted|sort) .{0,30}(differ|mismatch|unspecified|not guaranteed)|"
       r"(set|dict|map|hash) (iteration|ordering)|HashMap|unordered|in different order", 0.7,
       "unordered collection compared as ordered"),
    _r(C.DATA, r"\d\.\d{10,}", 0.6, "float representation artefact"),
    _r(C.DATA, r"expected:? ?<?\[?[\"']?\d{4}-\d{2}-\d{2}", 0.45, "hard-coded date in assertion"),
    _r(C.DATA, r"fixture data|test data|seed data|sample data|stale fixture|snapshot", 0.45,
       "test-data vocabulary"),
]
# fmt: on


class HeuristicClassifier:
    name = "heuristic"

    def classify(self, ev: Evidence) -> Classification:
        text = ev.text
        scores: dict[Cause, float] = {}
        hits: dict[Cause, list[str]] = {}
        for rule in RULES:
            if rule.pattern.search(text):
                prev = scores.get(rule.cause, 0.0)
                scores[rule.cause] = 1 - (1 - prev) * (1 - rule.weight)
                hits.setdefault(rule.cause, []).append(rule.label)
        if not scores:
            return Classification(
                category=Cause.UNKNOWN,
                confidence=0.0,
                rationale="No heuristic rule matched the failure text.",
                engine=self.name,
            )
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0].value))
        top_cause, top = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        if top < MIN_SCORE:
            return Classification(
                category=Cause.UNKNOWN,
                confidence=0.0,
                rationale=f"Best candidate ({top_cause.value}) scored {top:.2f}, below {MIN_SCORE}.",
                evidence=hits[top_cause],
                engine=self.name,
            )
        confidence = round(max(0.05, top * (1 - 0.6 * second)), 2)
        return Classification(
            category=top_cause,
            confidence=min(confidence, 0.99),
            rationale="Matched: " + "; ".join(hits[top_cause]),
            evidence=hits[top_cause],
            engine=self.name,
        )

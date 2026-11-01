"""DEV failure templates. The heuristic rules were tuned while looking at these.

SYNTHETIC: hand-written imitations of real failure output, not scraped from real CI logs.
Placeholders: {n} {m} (ints), {port}, {hex}, {email}.
"""

from __future__ import annotations

from typing import NamedTuple


class Tpl(NamedTuple):
    cause: str
    lang: str  # py | java | js
    exc: str
    msg: str
    frames: str = ""  # extra stack lines (selenium internals etc.)


SEL_WAIT = '  File "/opt/venv/lib/python3.11/site-packages/selenium/webdriver/support/wait.py", line 95, in until\n    raise TimeoutException(message, screen, stacktrace)'

DEV: list[Tpl] = [
    # ---- timing_wait ----
    Tpl("timing_wait", "py", "selenium.common.exceptions.TimeoutException", "Message:", SEL_WAIT),
    Tpl(
        "timing_wait",
        "java",
        "org.openqa.selenium.TimeoutException",
        "Expected condition failed: waiting for visibility of element located by By.id: submit-btn "
        "(tried for 10 second(s) with 500 milliseconds interval)",
    ),
    Tpl(
        "timing_wait",
        "java",
        "org.openqa.selenium.ElementClickInterceptedException",
        'element click intercepted: Element <button id="checkout-{n}" class="btn"> is not '
        "clickable at point ({n}, {m}). Other element would receive the click: "
        '<div class="modal-backdrop fade show"></div>',
    ),
    Tpl(
        "timing_wait",
        "py",
        "selenium.common.exceptions.NoSuchElementException",
        "Message: no such element: Unable to locate element: "
        '{{"method":"css selector","selector":"#results-table"}}',
    ),
    Tpl(
        "timing_wait",
        "js",
        "Error",
        "Timeout - Async callback was not invoked within the 5000 ms timeout specified by "
        "jest.setTimeout.",
    ),
    Tpl(
        "timing_wait",
        "js",
        "TimeoutError",
        "waiting for selector `#toast-{n}` failed: timeout 30000ms exceeded",
    ),
    Tpl("timing_wait", "py", "AssertionError", "assert 'Loading...' == 'Saved'"),
    Tpl(
        "timing_wait",
        "java",
        "org.openqa.selenium.ElementNotInteractableException",
        "element not interactable: element has zero size",
    ),
    # ---- stale_element ----
    Tpl(
        "stale_element",
        "java",
        "org.openqa.selenium.StaleElementReferenceException",
        "stale element reference: element is not attached to the page document\n"
        "  (Session info: chrome=118.0.{n}.70)",
    ),
    Tpl(
        "stale_element",
        "py",
        "selenium.common.exceptions.StaleElementReferenceException",
        "Message: stale element reference: stale element not found",
    ),
    Tpl(
        "stale_element",
        "js",
        "Error",
        "Execution context was destroyed, most likely because of a navigation.",
    ),
    Tpl(
        "stale_element",
        "java",
        "org.openqa.selenium.StaleElementReferenceException",
        "stale element reference: element is not attached to the page document for element: "
        "[[ChromeDriver: chrome on LINUX ({hex})] -> css selector: .row-{n}]",
    ),
    Tpl(
        "stale_element",
        "js",
        "Error",
        "cy.click() failed because this element is detached from the DOM.",
    ),
    # ---- network_env ----
    Tpl(
        "network_env",
        "py",
        "requests.exceptions.ConnectionError",
        "HTTPConnectionPool(host='api.staging.internal', port=8080): Max retries exceeded with "
        "url: /v1/orders/{n} (Caused by NewConnectionError('Failed to establish a new "
        "connection: [Errno 111] Connection refused'))",
    ),
    Tpl(
        "network_env",
        "java",
        "org.openqa.selenium.SessionNotCreatedException",
        "Could not start a new session. Response code 500. Message: session not created: "
        "Chrome failed to start: exited abnormally.",
    ),
    Tpl(
        "network_env",
        "java",
        "org.openqa.selenium.WebDriverException",
        "disconnected: not connected to DevTools\n  (failed to check if window was closed: "
        "disconnected: not connected to DevTools)",
    ),
    Tpl("network_env", "js", "Error", "connect ECONNREFUSED 127.0.0.1:{port}"),
    Tpl(
        "network_env",
        "py",
        "OSError",
        "[Errno 28] No space left on device: '/tmp/pytest-of-runner/pytest-{n}'",
    ),
    Tpl("network_env", "java", "java.net.SocketTimeoutException", "Read timed out"),
    Tpl("network_env", "js", "Error", "Request failed with status code 503"),
    Tpl(
        "network_env",
        "py",
        "selenium.common.exceptions.WebDriverException",
        "Message: unknown error: net::ERR_CONNECTION_RESET",
    ),
    # ---- shared_state ----
    Tpl("shared_state", "py", "sqlite3.OperationalError", "database is locked"),
    Tpl("shared_state", "java", "java.util.ConcurrentModificationException", ""),
    Tpl(
        "shared_state",
        "py",
        "AssertionError",
        "expected 3 orders but found 4 (leftover rows from another test in table orders)",
    ),
    Tpl("shared_state", "js", "Error", "listen EADDRINUSE: address already in use :::{port}"),
    Tpl(
        "shared_state",
        "py",
        "PermissionError",
        "[WinError 32] The process cannot access the file because it is being used by another "
        "process: 'C:\\\\tmp\\\\report_{n}.csv'",
    ),
    Tpl(
        "shared_state",
        "py",
        "psycopg2.errors.UniqueViolation",
        'duplicate key value violates unique constraint "users_email_key"\n'
        "DETAIL:  Key (email)=({email}) already exists.",
    ),
    # ---- order_dependence ----
    Tpl("order_dependence", "py", "KeyError", "'auth_token'"),
    Tpl(
        "order_dependence",
        "java",
        "java.lang.NullPointerException",
        'Cannot invoke "com.acme.shop.Cart.getItems()" because "this.cart" is null',
    ),
    Tpl(
        "order_dependence",
        "py",
        "psycopg2.errors.UndefinedTable",
        'relation "orders" does not exist',
    ),
    Tpl(
        "order_dependence",
        "py",
        "AssertionError",
        "state from a previous test was not present: expected 1 cart item, got 0",
    ),
    Tpl(
        "order_dependence", "js", "TypeError", "Cannot read properties of undefined (reading 'id')"
    ),
    Tpl(
        "order_dependence",
        "java",
        "java.lang.IllegalStateException",
        "Session not initialized - login test must run first (depends on LoginTest.login)",
    ),
    # ---- data ----
    Tpl(
        "data",
        "py",
        "AssertionError",
        "assert datetime.date(2024, 3, {n}) == datetime.date(2024, 3, {m})\n"
        " (timezone: runner is UTC, fixture assumes America/New_York)",
    ),
    Tpl(
        "data", "java", "java.lang.AssertionError", "expected:<[2024-01-31]> but was:<[2024-02-01]>"
    ),
    Tpl("data", "py", "AssertionError", "assert 0.30000000000000004 == 0.3"),
    Tpl(
        "data",
        "java",
        "java.lang.AssertionError",
        "expected: <[alice, bob, carol]> but was: <[carol, alice, bob]>",
    ),
    Tpl(
        "data",
        "js",
        "Error",
        'expect(received).toEqual(expected) // deep equality\n- Expected: ["b", "a"]\n'
        '+ Received: ["a", "b"]',
    ),
    Tpl(
        "data",
        "py",
        "AssertionError",
        "random sample collided: seed={n} produced duplicate username",
    ),
    Tpl("data", "py", "AssertionError", "assert 'Jan 5, 2025' == '05.01.2025' (locale mismatch)"),
]

GENERIC: list[Tpl] = [
    Tpl("generic", "py", "AssertionError", "assert False"),
    Tpl("generic", "py", "AssertionError", ""),
    Tpl("generic", "java", "java.lang.AssertionError", "expected [true] but found [false]"),
    Tpl(
        "generic",
        "js",
        "Error",
        "expect(received).toBe(expected) // Object.is equality\n\nExpected: true\nReceived: false",
    ),
]

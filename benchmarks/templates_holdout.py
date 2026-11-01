"""HOLDOUT templates.

Written AFTER the heuristic rules and the mock-LLM lexicon were frozen, with different
phrasing and exception families than the DEV set. The rules were not edited after the
holdout score was first computed. Still SYNTHETIC, and still written by the same author as the
rules, so treat holdout accuracy as optimistic for real-world logs.
"""

from __future__ import annotations

from .templates_dev import Tpl

HOLDOUT: list[Tpl] = [
    # ---- timing_wait ----
    Tpl(
        "timing_wait",
        "java",
        "org.openqa.selenium.NoSuchElementException",
        'no such element: Unable to locate element: {{"method":"xpath","selector":"//tr[@data-row=\'{n}\']"}}\n'
        "  For documentation on this error, please visit: https://selenium.dev/documentation",
    ),
    Tpl(
        "timing_wait",
        "py",
        "playwright._impl._errors.TimeoutError",
        'Locator.click: Timeout 30000ms exceeded.\nCall log:\n  - waiting for locator("button.save")\n'
        '  -   locator resolved to <button class="save" disabled>Save</button>\n  - element is not enabled',
    ),
    Tpl("timing_wait", "js", "Error", 'thrown: "Exceeded timeout of 5000 ms for a test."'),
    Tpl(
        "timing_wait",
        "py",
        "selenium.common.exceptions.ElementClickInterceptedException",
        'Message: element click intercepted: Element <a href="/cart"> is not clickable at point ({n}, {m})',
    ),
    Tpl(
        "timing_wait",
        "py",
        "AssertionError",
        "assert 'Please wait' in 'Processing order, please wait...'",
    ),
    Tpl(
        "timing_wait",
        "java",
        "org.openqa.selenium.TimeoutException",
        "Timed out after 15 seconds waiting for element to be clickable: By.cssSelector: .btn-primary",
    ),
    # ---- stale_element ----
    Tpl(
        "stale_element",
        "java",
        "org.openqa.selenium.StaleElementReferenceException",
        'The element reference of <li class="item"> is stale; either the element is no longer '
        "attached to the DOM, it is not in the current frame context, or the document has been refreshed",
    ),
    Tpl(
        "stale_element",
        "js",
        "Error",
        "Protocol error (Runtime.callFunctionOn): Cannot find context with specified id",
    ),
    Tpl(
        "stale_element",
        "py",
        "playwright._impl._errors.Error",
        "ElementHandle.click: Element is not attached to the DOM",
    ),
    Tpl(
        "stale_element",
        "py",
        "selenium.common.exceptions.StaleElementReferenceException",
        "Message: The element with the reference {hex} is stale; either its node document is not "
        "the active document, or it is no longer connected to the DOM",
    ),
    Tpl("stale_element", "js", "Error", "Element is detached from the document (nodeId {n})"),
    # ---- network_env ----
    Tpl(
        "network_env",
        "java",
        "java.net.UnknownHostException",
        "selenium-hub.ci.svc.cluster.local: Temporary failure in name resolution",
    ),
    Tpl(
        "network_env",
        "py",
        "urllib3.exceptions.ReadTimeoutError",
        "HTTPSConnectionPool(host='sso.example.com', port=443): Read timed out. (read timeout=10)",
    ),
    Tpl("network_env", "js", "Error", "socket hang up"),
    Tpl(
        "network_env",
        "py",
        "selenium.common.exceptions.WebDriverException",
        "Message: chrome not reachable\n  (Session info: chrome=119.0.{n}.58)",
    ),
    Tpl("network_env", "java", "java.lang.OutOfMemoryError", "Java heap space"),
    Tpl(
        "network_env",
        "py",
        "requests.exceptions.HTTPError",
        "502 Server Error: Bad Gateway for url: https://api.example.com/v1/search?q={n}",
    ),
    Tpl("network_env", "js", "Error", "getaddrinfo EAI_AGAIN registry.npmjs.org"),
    # ---- shared_state ----
    Tpl(
        "shared_state",
        "java",
        "org.springframework.dao.DeadlockLoserDataAccessException",
        "could not execute statement; SQL [n/a]; Deadlock found when trying to get lock; try restarting transaction",
    ),
    Tpl(
        "shared_state",
        "py",
        "AssertionError",
        "assert len(cache.entries()) == 0, 'cache contains entries from other tests: [{n}, {m}]'",
    ),
    Tpl(
        "shared_state",
        "java",
        "java.lang.AssertionError",
        "Singleton AppConfig still has overrides from a different test class: expected:<DEFAULT> but was:<MOCK_{n}>",
    ),
    Tpl("shared_state", "py", "OSError", "[Errno 98] Address already in use"),
    Tpl(
        "shared_state",
        "js",
        "Error",
        "ENOENT: no such file or directory, open '/tmp/fixtures/session-{n}.json'",
    ),
    Tpl(
        "shared_state",
        "py",
        "AssertionError",
        "assert 7 == 5\n  +  where 7 = count_rows('invoices')  # rows inserted by parallel xdist workers",
    ),
    # ---- order_dependence ----
    Tpl(
        "order_dependence",
        "py",
        "AssertionError",
        "assert user_service.current_user() is not None  # test_logout runs before this one under random ordering",
    ),
    Tpl(
        "order_dependence",
        "java",
        "org.testng.TestException",
        "Method CartTest.addItem() depends on not successfully finished methods [LoginTest.login]",
    ),
    Tpl(
        "order_dependence",
        "py",
        "pytest.fail.Exception",
        "fixture 'seeded_catalog' was not populated; setup_module never ran",
    ),
    Tpl(
        "order_dependence",
        "js",
        "Error",
        "Test suite state is uninitialized: run order of describe blocks changed",
    ),
    Tpl(
        "order_dependence",
        "py",
        "AssertionError",
        "assert counter.value == 1  # passes in isolation, got {n} in full run",
    ),
    Tpl("order_dependence", "java", "java.lang.AssertionError", "expected:<0> but was:<{n}>"),
    # ---- data ----
    Tpl(
        "data",
        "py",
        "AssertionError",
        "assert order.created_at.date() == date.today()  # DST transition: 2025-03-09 vs 2025-03-10 off by one day",
    ),
    Tpl(
        "data",
        "java",
        "org.opentest4j.AssertionFailedError",
        "expected: <1,234.50> but was: <1.234,50> (default locale differs on this runner)",
    ),
    Tpl("data", "py", "AssertionError", "assert 19.989999999999998 == 19.99"),
    Tpl(
        "data",
        "java",
        "java.lang.AssertionError",
        'Expected: iterable containing ["east", "west"] in order but: item 0: was "west" (HashMap iteration)',
    ),
    Tpl("data", "js", "Error", "Faker generated a name containing an apostrophe: O'Brien-{n}"),
    Tpl(
        "data",
        "py",
        "AssertionError",
        "assert 'zoé' == 'zoe\\u0301'  # unicode normalization of fixture name",
    ),
]

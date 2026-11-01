<!-- flakewatch-report -->
## flakewatch report

**3 flaky** · 1 consistently failing · 1 stable · 0 with too little history — 5 run(s) analysed, flaky threshold 0.1

### Flaky tests

| Test | Score | Flip rate | Passed on retry | Probable cause | Conf. | Quarantined |
|---|---:|---:|---:|---|---:|:-:|
| `tests.ui.test_grid::test_row_text` | 1.00 | 1.00 | 0 | stale element | 99% | yes |
| `com.acme.CartTest::addItem` | 0.80 | 0.00 | 2 | timing / wait | 88% | yes |
| `tests.api.test_orders::test_create` | 0.75 | 0.75 | 0 | network / env | 99% | yes |

### Details

<details>
<summary><code>tests.ui.test_grid::test_row_text</code> — stale element</summary>

- runs: 5, failures: 3, flips: 4, same-commit pass+fail: yes
- why: Matched: StaleElementReferenceException; 'stale element' message; element detached from page (engine: heuristic)
- suggested fix: Do not cache WebElements across page updates; re-locate on use or wrap the action in a retry-on-stale helper / `ExpectedConditions.refreshed`.
- `60beae1824` ×3: `org.openqa.selenium.StaleElementReferenceException stale element reference: element is not attached to the page document`

</details>

<details>
<summary><code>com.acme.CartTest::addItem</code> — timing / wait</summary>

- runs: 5, failures: 0, flips: 0, same-commit pass+fail: no
- why: Matched: Selenium TimeoutException; explicit wait expired (engine: heuristic)
- suggested fix: Replace sleeps/implicit waits with explicit waits on the exact condition (clickable, text present, network idle); wait for overlays/animations to finish.
- `805821547f` ×2: `org.openqa.selenium.TimeoutException Expected condition failed: waiting for visibility of element located by By.id: go`

</details>

<details>
<summary><code>tests.api.test_orders::test_create</code> — network / env</summary>

- runs: 5, failures: 2, flips: 3, same-commit pass+fail: yes
- why: Matched: connection error; HTTP/socket timeout (engine: heuristic)
- suggested fix: Stub external calls, pin/health-check dependencies, and give the runner enough memory/disk; treat browser crashes as infra, not test bugs.
- `3ad6e5a0fb` ×2: `requests.exceptions.ConnectionError HTTPConnectionPool(host='api', port=8080): Max retries exceeded (Connection refused)`

</details>

### Consistently failing (not flaky)

- `tests.test_checkout::test_total` — failing in every recent run (3 failures)

_3 test(s) currently quarantined (entries expire; still-flaky tests are re-added on the next `flakewatch quarantine`)._

<sub>flakewatch · classifier: heuristic · generated 2025-01-01T00:00:00Z</sub>

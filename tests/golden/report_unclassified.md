<!-- flakewatch-report -->
## flakewatch report

**3 flaky** · 1 consistently failing · 1 stable · 0 with too little history — 5 run(s) analysed, flaky threshold 0.1

### Flaky tests

| Test | Score | Flip rate | Passed on retry | Probable cause | Conf. | Quarantined |
|---|---:|---:|---:|---|---:|:-:|
| `tests.ui.test_grid::test_row_text` | 1.00 | 1.00 | 0 | - | - |  |
| `com.acme.CartTest::addItem` | 0.80 | 0.00 | 2 | - | - |  |
| `tests.api.test_orders::test_create` | 0.75 | 0.75 | 0 | - | - |  |

### Details

<details>
<summary><code>tests.ui.test_grid::test_row_text</code> — unclassified</summary>

- runs: 5, failures: 3, flips: 4, same-commit pass+fail: yes
- `60beae1824` ×3: `org.openqa.selenium.StaleElementReferenceException stale element reference: element is not attached to the page document`

</details>

<details>
<summary><code>com.acme.CartTest::addItem</code> — unclassified</summary>

- runs: 5, failures: 0, flips: 0, same-commit pass+fail: no
- `805821547f` ×2: `org.openqa.selenium.TimeoutException Expected condition failed: waiting for visibility of element located by By.id: go`

</details>

<details>
<summary><code>tests.api.test_orders::test_create</code> — unclassified</summary>

- runs: 5, failures: 2, flips: 3, same-commit pass+fail: yes
- `3ad6e5a0fb` ×2: `requests.exceptions.ConnectionError HTTPConnectionPool(host='api', port=8080): Max retries exceeded (Connection refused)`

</details>

### Consistently failing (not flaky)

- `tests.test_checkout::test_total` — failing in every recent run (3 failures)

<sub>flakewatch · classifier: not classified · generated 2025-01-01T00:00:00Z</sub>

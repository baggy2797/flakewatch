"""Markdown (PR comment / job summary) and JSON rendering."""

from __future__ import annotations

from pathlib import Path

from .models import Cause, FlakyTest, QuarantineFile, Report

MARKER = "<!-- flakewatch-report -->"
MAX_ROWS = 25

CAUSE_LABEL = {
    Cause.TIMING_WAIT: "timing / wait",
    Cause.STALE_ELEMENT: "stale element",
    Cause.ORDER_DEPENDENCE: "order dependence",
    Cause.SHARED_STATE: "shared state",
    Cause.NETWORK_ENV: "network / env",
    Cause.DATA: "test data",
    Cause.UNKNOWN: "unknown",
}
CAUSE_HINT = {
    Cause.TIMING_WAIT: "Replace sleeps/implicit waits with explicit waits on the exact "
    "condition (clickable, text present, network idle); wait for overlays/animations to finish.",
    Cause.STALE_ELEMENT: "Do not cache WebElements across page updates; re-locate on use or "
    "wrap the action in a retry-on-stale helper / `ExpectedConditions.refreshed`.",
    Cause.ORDER_DEPENDENCE: "Make the test create its own preconditions; run the suite with a "
    "random order (pytest-randomly, TestNG `preserve-order=false`) to reproduce.",
    Cause.SHARED_STATE: "Isolate per-test resources (unique DB schema/rows, tmp dirs, "
    "ephemeral ports); reset singletons/caches in teardown; avoid parallel writes to one resource.",
    Cause.NETWORK_ENV: "Stub external calls, pin/health-check dependencies, and give the "
    "runner enough memory/disk; treat browser crashes as infra, not test bugs.",
    Cause.DATA: "Freeze clocks and timezones, seed RNGs, sort before comparing unordered "
    "collections, and use tolerance for floats.",
    Cause.UNKNOWN: "Not enough signal in the failure text; capture screenshots/logs on failure.",
}


def to_json(report: Report) -> str:
    return report.model_dump_json(indent=2) + "\n"


def load_report(path: Path) -> Report:
    return Report.model_validate_json(path.read_text(encoding="utf-8"))


def _esc(text: str, limit: int = 90) -> str:
    text = " ".join(text.split()).replace("|", "\\|").replace("`", "'")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _cause_cell(t: FlakyTest) -> tuple[str, str]:
    c = t.classification
    if not c:
        return "-", "-"
    return CAUSE_LABEL[c.category], f"{c.confidence:.0%}"


def render_markdown(report: Report, quarantine: QuarantineFile | None = None) -> str:
    flaky = [t for t in report.tests if t.metrics.verdict == "flaky"]
    broken = [t for t in report.tests if t.metrics.verdict == "broken"]
    q_ids = {e.test_id for e in quarantine.entries} if quarantine else set()
    tot = report.totals
    lines = [MARKER, "## flakewatch report", ""]
    if not flaky and not broken:
        lines += [
            f"No flaky tests detected across {report.window_runs} run(s) "
            f"({tot.get('tests', 0)} tests analysed).",
            "",
        ]
        return "\n".join(lines) + "\n"
    lines += [
        f"**{len(flaky)} flaky** · {len(broken)} consistently failing · "
        f"{tot.get('stable', 0)} stable · {tot.get('insufficient', 0)} with too little history "
        f"— {report.window_runs} run(s) analysed, flaky threshold {report.threshold}",
        "",
    ]
    if flaky:
        lines += [
            "### Flaky tests",
            "",
            "| Test | Score | Flip rate | Passed on retry | Probable cause | Conf. | Quarantined |",
            "|---|---:|---:|---:|---|---:|:-:|",
        ]
        for t in flaky[:MAX_ROWS]:
            cause, conf = _cause_cell(t)
            m = t.metrics
            lines.append(
                f"| `{_esc(t.test_id, 70)}` | {m.score:.2f} | {m.flip_rate:.2f} | "
                f"{m.retry_pass_runs} | {cause} | {conf} | {'yes' if t.test_id in q_ids else ''} |"
            )
        if len(flaky) > MAX_ROWS:
            lines.append(f"\n…and {len(flaky) - MAX_ROWS} more (see the JSON report).")
        lines.append("")
    if report.clusters:
        lines += [
            "### Shared failure signatures",
            "",
            "Several flaky tests fail with the same normalised error, which usually points at "
            "one shared cause (environment, fixture, page object) rather than N test bugs.",
            "",
            "| Signature | Tests | Occurrences | Error |",
            "|---|---:|---:|---|",
        ]
        for cl in report.clusters[:10]:
            lines.append(
                f"| `{cl.signature}` | {len(cl.tests)} | {cl.occurrences} | "
                f"{_esc(cl.exc_type + ': ' + cl.message, 80)} |"
            )
        lines.append("")
    if flaky:
        lines += ["### Details", ""]
        for t in flaky[:MAX_ROWS]:
            m = t.metrics
            c = t.classification
            lines += [
                "<details>",
                f"<summary><code>{_esc(t.test_id, 100)}</code> — "
                f"{CAUSE_LABEL[c.category] if c else 'unclassified'}</summary>",
                "",
                f"- runs: {m.runs}, failures: {m.failures}, flips: {m.flips}, "
                f"same-commit pass+fail: {'yes' if m.same_commit_mixed else 'no'}",
            ]
            if c:
                lines.append(f"- why: {_esc(c.rationale, 200)} (engine: {c.engine})")
                lines.append(f"- suggested fix: {CAUSE_HINT[c.category]}")
            for s in t.signatures[:2]:
                lines.append(
                    f"- `{s.signature}` ×{s.count}: `{_esc(s.exc_type + ' ' + s.message, 140)}`"
                )
            lines += ["", "</details>", ""]
    if broken:
        lines += [
            "### Consistently failing (not flaky)",
            "",
            *[
                f"- `{_esc(t.test_id, 100)}` — failing in every recent run ({t.metrics.failures} failures)"
                for t in broken[:10]
            ],
            "",
        ]
    if quarantine and quarantine.entries:
        lines += [
            f"_{len(quarantine.entries)} test(s) currently quarantined (entries expire; "
            "still-flaky tests are re-added on the next `flakewatch quarantine`)._",
            "",
        ]
    eng = report.classify_engine or "not classified"
    lines.append(f"<sub>flakewatch · classifier: {eng} · generated {report.generated_at}</sub>")
    return "\n".join(lines) + "\n"

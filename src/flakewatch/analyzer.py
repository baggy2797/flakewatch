"""Flakiness metrics over the run history."""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import datetime, timezone

from .models import (
    CaseResult,
    Cluster,
    FlakyTest,
    Metrics,
    Report,
    RunInfo,
    SignatureStat,
    Status,
)
from .signatures import signature
from .store import HistoryStore

DEFAULT_WINDOW = 50
DEFAULT_THRESHOLD = 0.1
MIN_RUNS = 3
TAIL_BROKEN = 3


def now_iso() -> str:
    """UTC timestamp; honours SOURCE_DATE_EPOCH for reproducible reports."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    dt = (
        datetime.fromtimestamp(int(epoch), tz=timezone.utc)
        if epoch and epoch.isdigit()
        else datetime.now(tz=timezone.utc)
    )
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_metrics(history: list[tuple[RunInfo, CaseResult]], threshold: float) -> Metrics:
    """Score one test from its chronological (run, result) history.

    flip_rate    = outcome changes / (observed runs - 1)
    score        = 1 - (1 - flip_rate) * (1 - min(1, 2 * retry_pass_rate)); floored at 0.6 when
                   the same commit both passed and failed (strongest evidence of non-determinism)
    A test whose last TAIL_BROKEN outcomes are all failures with <= 1 flip is "broken", not flaky.
    """
    obs = [(run, r) for run, r in history if r.status != Status.SKIPPED]
    outcomes = [r.status == Status.PASSED for _, r in obs]
    n = len(obs)
    passes = sum(outcomes)
    failures = n - passes
    flips = sum(1 for a, b in zip(outcomes, outcomes[1:], strict=False) if a != b)
    flip_rate = flips / (n - 1) if n > 1 else 0.0
    retry_runs = sum(1 for _, r in obs if r.retried_pass)
    by_commit: dict[str, set[bool]] = defaultdict(set)
    for run, r in obs:
        if run.commit_sha:
            by_commit[run.commit_sha].add(r.status == Status.PASSED)
    same_commit_mixed = any(len(v) == 2 for v in by_commit.values())

    mixed = passes > 0 and failures > 0
    flip_part = flip_rate if mixed else 0.0
    retry_part = min(1.0, 2 * retry_runs / n) if n else 0.0
    score = 1 - (1 - flip_part) * (1 - retry_part)
    if same_commit_mixed:
        score = max(score, 0.6)
    if retry_runs:
        score = max(score, 0.3)

    tail = outcomes[-TAIL_BROKEN:]
    broken = len(tail) == TAIL_BROKEN and not any(tail) and flips <= 1 and retry_runs == 0
    if broken and not same_commit_mixed:
        verdict = "broken"
    elif n < MIN_RUNS and not retry_runs and not same_commit_mixed:
        verdict = "insufficient"
    elif failures == 0 and not retry_runs:
        verdict = "stable"
    elif score >= threshold:
        verdict = "flaky"
    else:
        verdict = "stable"
    return Metrics(
        runs=n,
        passes=passes,
        failures=failures,
        fail_rate=round(failures / n, 4) if n else 0.0,
        flips=flips,
        flip_rate=round(flip_rate, 4),
        retry_pass_runs=retry_runs,
        same_commit_mixed=same_commit_mixed,
        score=round(score, 4),
        verdict=verdict,
    )


def _signatures(history: list[tuple[RunInfo, CaseResult]]) -> list[SignatureStat]:
    counts: Counter[str] = Counter()
    example: dict[str, CaseResult] = {}
    for _, r in history:
        if r.fail_message or r.fail_type:
            sig = signature(r.fail_type, r.fail_message, r.fail_trace)
            counts[sig] += 1
            example.setdefault(sig, r)
    stats = []
    for sig, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        ex = example[sig]
        stats.append(
            SignatureStat(
                signature=sig,
                count=count,
                exc_type=ex.fail_type or "",
                message=ex.fail_message or "",
                trace=ex.fail_trace or "",
            )
        )
    return stats[:3]


def analyze(
    store: HistoryStore,
    window: int = DEFAULT_WINDOW,
    threshold: float = DEFAULT_THRESHOLD,
    include: set[str] | None = None,
) -> Report:
    """Compute a Report from the latest `window` runs in the store."""
    runs = store.runs(window)
    rows = store.results_for([r.run_id for r in runs])
    order = {r.run_id: i for i, r in enumerate(runs)}
    per_test: dict[str, list[tuple[RunInfo, CaseResult]]] = defaultdict(list)
    for run, res in sorted(rows, key=lambda x: order[x[0].run_id]):
        per_test[res.test_id].append((run, res))

    totals: Counter[str] = Counter()
    tests: list[FlakyTest] = []
    for test_id, history in per_test.items():
        m = compute_metrics(history, threshold)
        totals[m.verdict] += 1
        if m.verdict in {"flaky", "broken"}:
            tests.append(
                FlakyTest(
                    test_id=test_id,
                    framework=history[-1][1].framework,
                    metrics=m,
                    signatures=_signatures(history),
                )
            )
    tests.sort(key=lambda t: (t.metrics.verdict != "flaky", -t.metrics.score, t.test_id))

    sig_tests: dict[str, set[str]] = defaultdict(set)
    sig_info: dict[str, SignatureStat] = {}
    sig_occ: Counter[str] = Counter()
    for t in tests:
        if t.metrics.verdict != "flaky":
            continue
        for s in t.signatures:
            sig_tests[s.signature].add(t.test_id)
            sig_info.setdefault(s.signature, s)
            sig_occ[s.signature] += s.count
    clusters = [
        Cluster(
            signature=sig,
            exc_type=sig_info[sig].exc_type,
            message=sig_info[sig].message[:200],
            tests=sorted(ids),
            occurrences=sig_occ[sig],
        )
        for sig, ids in sig_tests.items()
        if len(ids) >= 2
    ]
    clusters.sort(key=lambda c: (-len(c.tests), -c.occurrences, c.signature))

    summary = {k: totals.get(k, 0) for k in ("flaky", "broken", "stable", "insufficient")}
    summary["tests"] = sum(summary.values())
    return Report(
        generated_at=now_iso(),
        window_runs=len(runs),
        run_ids=[r.run_id for r in runs],
        totals=summary,
        threshold=threshold,
        tests=tests if include is None else [t for t in tests if t.test_id in include],
        clusters=clusters,
    )

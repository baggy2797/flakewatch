from __future__ import annotations

import pytest

from flakewatch.analyzer import analyze, compute_metrics, now_iso
from flakewatch.models import CaseResult, RunInfo, Status
from flakewatch.store import HistoryStore


def hist(outcomes: str, commits: str | None = None, retried: str = ""):
    """'PFPF' -> history. commits e.g. 'aabb' gives per-run commit; retried marks runs 'r'."""
    out = []
    for i, ch in enumerate(outcomes):
        status = {"P": Status.PASSED, "F": Status.FAILED, "S": Status.SKIPPED}[ch]
        run = RunInfo(run_id=f"r{i}", timestamp=i, commit_sha=commits[i] if commits else f"c{i}")
        out.append(
            (
                run,
                CaseResult(
                    test_id="t", status=status, retried_pass=bool(retried) and retried[i] == "r"
                ),
            )
        )
    return out


def test_alternating_is_flaky():
    m = compute_metrics(hist("PFPFPFPF"), 0.1)
    assert m.verdict == "flaky" and m.flip_rate == 1.0 and m.flips == 7


def test_all_pass_is_stable():
    m = compute_metrics(hist("PPPPP"), 0.1)
    assert m.verdict == "stable" and m.score == 0.0


def test_regression_is_broken_not_flaky():
    m = compute_metrics(hist("PPPPFFFF"), 0.1)
    assert m.verdict == "broken" and m.flips == 1


def test_single_old_failure_below_threshold_is_stable():
    m = compute_metrics(hist("PPPPPPPPPPFPPPPPPPPPPPPPPPPPPP"), 0.1)
    assert m.verdict == "stable" and m.failures == 1


def test_same_commit_mixed_floors_score():
    m = compute_metrics(hist("PPFPP", commits="aabcd"), 0.1)  # pass+pass on a, fail on b
    assert not m.same_commit_mixed
    m2 = compute_metrics(hist("PFPPP", commits="aabcd"), 0.1)
    assert m2.same_commit_mixed and m2.score >= 0.6 and m2.verdict == "flaky"


def test_pass_after_retry_alone_is_flaky():
    m = compute_metrics(hist("PPPP", retried="r---"), 0.1)
    assert m.retry_pass_runs == 1 and m.verdict == "flaky" and m.score >= 0.3


def test_insufficient_history():
    assert compute_metrics(hist("PF"), 0.1).verdict == "insufficient"
    assert compute_metrics([], 0.1).verdict == "insufficient"


def test_skipped_runs_ignored():
    m = compute_metrics(hist("PSSFPFP"), 0.1)
    assert m.runs == 5


def test_analyze_report_structure(golden_store):
    rep = analyze(golden_store)
    assert rep.window_runs == 5
    verdicts = {t.test_id: t.metrics.verdict for t in rep.tests}
    assert verdicts["tests.ui.test_grid::test_row_text"] == "flaky"
    assert verdicts["com.acme.CartTest::addItem"] == "flaky"
    assert verdicts["tests.test_checkout::test_total"] == "broken"
    assert rep.totals["stable"] == 1 and rep.totals["tests"] == 5
    assert rep.tests[0].metrics.verdict == "flaky"


def test_analyze_window_limits_runs(golden_store):
    assert analyze(golden_store, window=2).window_runs == 2


def test_clusters_group_shared_signature():
    s = HistoryStore(":memory:")
    for i in range(6):
        res = [
            CaseResult(
                test_id=f"t{k}",
                status=Status.FAILED if (i + k) % 2 else Status.PASSED,
                fail_type="ConnectionError",
                fail_message="Connection refused port 80",
                fail_trace="",
            )
            for k in range(3)
        ]
        s.ingest(RunInfo(run_id=f"r{i}", timestamp=i, commit_sha=f"c{i}"), res)
    rep = analyze(s)
    s.close()
    assert len(rep.clusters) == 1 and len(rep.clusters[0].tests) == 3


def test_now_iso_honours_source_date_epoch(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    assert now_iso() == "1970-01-01T00:00:00Z"
    monkeypatch.delenv("SOURCE_DATE_EPOCH")
    assert now_iso().endswith("Z")


@pytest.mark.parametrize("threshold,expected", [(0.05, "flaky"), (0.9, "stable")])
def test_threshold_is_configurable(threshold, expected):
    assert compute_metrics(hist("PPFPPPPPPP"), threshold).verdict == expected

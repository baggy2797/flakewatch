"""Run the full pipeline on the SYNTHETIC corpus and score detection + classification.

python -m benchmarks.run_benchmark [--seed 1337] [--out benchmarks/results.json]
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from flakewatch.analyzer import analyze
from flakewatch.classify import (
    Classifier,
    HeuristicClassifier,
    LLMClassifier,
    MockLLMClient,
    evidence_for,
)
from flakewatch.models import CaseResult, FlakyTest, RunInfo
from flakewatch.parser import merge_attempts, parse_junit
from flakewatch.store import HistoryStore

from .gen_corpus import CAUSES, build

LABELS = [*CAUSES, "unknown"]


def ingest_corpus(corpus: Path, labels: dict[str, Any]) -> HistoryStore:
    store = HistoryStore(":memory:")
    for run in labels["runs"]:
        results: list[CaseResult] = []
        for f in sorted((corpus / run["run_id"]).glob("*.xml")):
            res, _ = parse_junit(f)
            results.extend(res)
        store.ingest(
            RunInfo(run_id=run["run_id"], commit_sha=run["commit"], timestamp=run["timestamp"]),
            merge_attempts(results),
        )
    return store


def score_classifier(
    clf: Classifier, detected: list[FlakyTest], truth: dict[str, Any]
) -> dict[str, Any]:
    confusion: dict[str, Counter[str]] = {c: Counter() for c in CAUSES}
    by_split: dict[str, list[int]] = {"dev": [0, 0], "holdout": [0, 0], "all": [0, 0]}
    answered = correct_answered = 0
    amb_total = amb_correct = 0
    for t in detected:
        lab = truth[t.test_id]
        if lab["kind"] != "flaky":
            continue
        pred = clf.classify(evidence_for(t)).category.value
        ok = pred == lab["cause"]
        confusion[lab["cause"]][pred] += 1
        for key in ("all", lab["split"]):
            by_split[key][0] += ok
            by_split[key][1] += 1
        if pred != "unknown":
            answered += 1
            correct_answered += ok
        if lab["ambiguous"]:
            amb_total += 1
            amb_correct += ok
    n = by_split["all"][1]
    per_class = {}
    for c in CAUSES:
        tp = confusion[c][c]
        fn = sum(confusion[c].values()) - tp
        fp = sum(confusion[o][c] for o in CAUSES if o != c)
        per_class[c] = {
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "support": tp + fn,
        }
    return {
        "n": n,
        "accuracy": round(by_split["all"][0] / n, 3) if n else 0,
        "accuracy_dev": round(by_split["dev"][0] / by_split["dev"][1], 3)
        if by_split["dev"][1]
        else None,
        "accuracy_holdout": round(by_split["holdout"][0] / by_split["holdout"][1], 3)
        if by_split["holdout"][1]
        else None,
        "n_dev": by_split["dev"][1],
        "n_holdout": by_split["holdout"][1],
        "answered_rate": round(answered / n, 3) if n else 0,
        "accuracy_when_answered": round(correct_answered / answered, 3) if answered else None,
        "ambiguous_tests": amb_total,
        "per_class": per_class,
        "confusion": {c: dict(v) for c, v in confusion.items()},
    }


def run(seed: int = 1337, **kw: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        corpus = Path(tmp)
        labels = build(corpus, seed=seed, **kw)
        store = ingest_corpus(corpus, labels)
        try:
            report = analyze(store)
        finally:
            store.close()
    truth = labels["tests"]
    flagged = {t.test_id for t in report.tests if t.metrics.verdict == "flaky"}
    actual = {k for k, v in truth.items() if v["kind"] == "flaky"}
    tp, fp, fn = len(flagged & actual), len(flagged - actual), len(actual - flagged)
    detection = {
        "flaky_tests_labelled": len(actual),
        "flagged": len(flagged),
        "precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "false_positives_by_kind": dict(Counter(truth[t]["kind"] for t in flagged - actual)),
    }
    detected = [t for t in report.tests if t.test_id in flagged]
    return {
        "seed": seed,
        "synthetic": True,
        "runs": len(labels["runs"]),
        "tests": len(truth),
        "detection": detection,
        "classification": {
            "heuristic": score_classifier(HeuristicClassifier(), detected, truth),
            "mock-llm": score_classifier(LLMClassifier(MockLLMClient()), detected, truth),
        },
    }


def sweep(n: int) -> None:
    """Mean/min/max of headline metrics over seeds 1..n (shows seed-to-seed variance)."""
    import statistics

    rows = [run(s) for s in range(1, n + 1)]
    for eng in ("heuristic", "mock-llm"):
        for key in ("accuracy", "accuracy_dev", "accuracy_holdout", "accuracy_when_answered"):
            v = [r["classification"][eng][key] for r in rows]
            print(
                f"{eng:9s} {key:24s} mean={statistics.mean(v):.3f} min={min(v):.3f} max={max(v):.3f}"
            )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sweep", type=int, metavar="N", help="report variance over seeds 1..N")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--out", type=Path, default=Path("benchmarks/results.json"))
    a = ap.parse_args()
    if a.sweep:
        sweep(a.sweep)
        return
    res = run(a.seed)
    a.out.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "classification"}, indent=1))
    for eng, s in res["classification"].items():
        print(
            f"{eng:10s} acc={s['accuracy']} dev={s['accuracy_dev']} holdout={s['accuracy_holdout']} "
            f"answered={s['answered_rate']} acc|answered={s['accuracy_when_answered']} n={s['n']}"
        )


if __name__ == "__main__":
    main()

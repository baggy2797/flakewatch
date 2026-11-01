from __future__ import annotations

import json

from benchmarks import gen_corpus
from benchmarks.run_benchmark import run


def test_corpus_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    kw = dict(seed=3, runs=6, n_stable=5, per_cause=2, n_broken=1)
    gen_corpus.build(a, **kw)
    gen_corpus.build(b, **kw)
    files = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    assert files and all((a / f).read_bytes() == (b / f).read_bytes() for f in files)
    labels = json.loads((a / "labels.json").read_text())
    assert labels["synthetic"] is True
    assert {v["kind"] for v in labels["tests"].values()} == {"stable", "flaky", "broken"}


def test_different_seed_changes_corpus(tmp_path):
    kw = dict(runs=6, n_stable=5, per_cause=2, n_broken=1)
    l1 = gen_corpus.build(tmp_path / "a", seed=1, **kw)
    l2 = gen_corpus.build(tmp_path / "b", seed=2, **kw)
    assert l1["tests"].keys() != l2["tests"].keys()


def test_benchmark_floor_regression_guard():
    """Not a quality claim - guards against accidental rule regressions on the synthetic set."""
    res = run(seed=1337)
    assert res["detection"]["recall"] >= 0.9 and res["detection"]["precision"] >= 0.9
    h = res["classification"]["heuristic"]
    assert h["accuracy"] >= 0.55 and h["accuracy_when_answered"] >= 0.9
    assert res["classification"]["mock-llm"]["accuracy"] >= 0.3
    # the committed results file must match what the code produces today
    committed = json.loads(
        (
            __import__("pathlib").Path(__file__).parent.parent / "benchmarks" / "results.json"
        ).read_text()
    )
    assert committed == json.loads(json.dumps(res))

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flakewatch.cli import app
from flakewatch.models import Report

from .conftest import golden_runs

runner = CliRunner()
SAMPLE = Path(__file__).parent.parent / "examples" / "sample"


@pytest.fixture
def run_dirs(tmp_path):
    dirs = []
    for run, xml in golden_runs():
        d = tmp_path / "xml" / run.run_id
        d.mkdir(parents=True)
        (d / "junit.xml").write_text(xml, encoding="utf-8")
        dirs.append((run, d))
    return dirs


def ingest_all(run_dirs, db, extra=()):
    last = None
    for run, d in run_dirs:
        last = runner.invoke(
            app,
            [
                "analyze",
                str(d),
                "--db",
                str(db),
                "--run-id",
                run.run_id,
                "--commit",
                run.commit_sha,
                "--timestamp",
                str(run.timestamp),
                *extra,
            ],
        )
        assert last.exit_code in (0, 1), last.output
    return last


def test_version_and_help():
    assert runner.invoke(app, ["--version"]).output.strip() == "0.1.0"
    assert "analyze" in runner.invoke(app, ["--help"]).output


def test_end_to_end_pipeline(run_dirs, tmp_path):
    db, rep, md = tmp_path / "h.db", tmp_path / "r.json", tmp_path / "r.md"
    res = ingest_all(
        run_dirs, db, ["--json-out", str(rep), "--md-out", str(md), "--engine", "none"]
    )
    assert "3 flaky" in res.output
    report = Report.model_validate_json(rep.read_text())
    assert all(t.classification is None for t in report.tests)

    out = runner.invoke(app, ["classify", str(rep), "--engine", "heuristic"])
    assert out.exit_code == 0 and "classified 3" in out.output
    report = Report.model_validate_json(rep.read_text())
    cats = {t.test_id: t.classification.category.value for t in report.tests if t.classification}
    assert cats["tests.ui.test_grid::test_row_text"] == "stale_element"

    qf = tmp_path / "q.json"
    out = runner.invoke(
        app,
        ["quarantine", str(rep), "--file", str(qf), "--emit", "surefire", "--today", "2025-01-01"],
    )
    assert out.exit_code == 0 and "!com.acme.CartTest#addItem" in out.output
    assert len(json.loads(qf.read_text())["entries"]) == 3

    out = runner.invoke(app, ["comment", str(rep), "--quarantine-file", str(qf)])
    assert out.exit_code == 0 and "flakewatch report" in out.output and "| yes |" in out.output


def test_mock_llm_flag(run_dirs, tmp_path):
    rep = tmp_path / "r.json"
    ingest_all(run_dirs, tmp_path / "h.db", ["--json-out", str(rep), "--mock-llm"])
    assert Report.model_validate_json(rep.read_text()).classify_engine == "mock-llm"
    assert (
        runner.invoke(
            app, ["classify", str(rep), "--mock-llm", "--out", str(tmp_path / "o.json")]
        ).exit_code
        == 0
    )


def test_stdout_when_no_outputs_and_analyze_existing_db(run_dirs, tmp_path):
    db = tmp_path / "h.db"
    ingest_all(run_dirs, db, ["--json-out", str(tmp_path / "x.json")])
    res = runner.invoke(app, ["analyze", "--db", str(db)])
    assert "## flakewatch report" in res.stdout


def test_fail_on_flaky_respects_quarantine(run_dirs, tmp_path):
    db, rep, qf = tmp_path / "h.db", tmp_path / "r.json", tmp_path / "q.json"
    ingest_all(run_dirs, db, ["--json-out", str(rep)])
    res = runner.invoke(app, ["analyze", "--db", str(db), "--fail-on-flaky"])
    assert res.exit_code == 1
    runner.invoke(app, ["quarantine", str(rep), "--file", str(qf), "--min-score", "0"])
    res = runner.invoke(
        app, ["analyze", "--db", str(db), "--fail-on-flaky", "--quarantine-file", str(qf)]
    )
    assert res.exit_code == 0


def test_summary_writes_step_summary(run_dirs, tmp_path, monkeypatch):
    summ = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summ))
    ingest_all(run_dirs, tmp_path / "h.db", ["--summary"])
    assert "flakewatch report" in summ.read_text()


def test_github_env_defaults_for_run_id(run_dirs, tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "555")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    monkeypatch.setenv("GITHUB_SHA", "f" * 40)
    _, d = run_dirs[0]
    db = tmp_path / "h.db"
    assert runner.invoke(app, ["analyze", str(d), "--db", str(db)]).exit_code == 0
    from flakewatch.store import HistoryStore

    s = HistoryStore(db)
    assert [r.run_id for r in s.runs()] == ["555-2"] and s.runs()[0].commit_sha == "f" * 40
    s.close()


def test_local_run_id_is_content_hash(run_dirs, tmp_path, monkeypatch):
    # CI sets GITHUB_RUN_ID; this test is about the local fallback, so it must not depend on the environment.
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    monkeypatch.delenv("GITHUB_RUN_ATTEMPT", raising=False)
    _, d = run_dirs[0]
    db = tmp_path / "h.db"
    runner.invoke(app, ["analyze", str(d), "--db", str(db)])
    runner.invoke(app, ["analyze", str(d), "--db", str(db)])
    from flakewatch.store import HistoryStore

    s = HistoryStore(db)
    assert len(s.runs()) == 1 and s.runs()[0].run_id.startswith("local-")
    s.close()


def test_errors(tmp_path):
    res = runner.invoke(app, ["analyze", str(tmp_path / "missing"), "--db", str(tmp_path / "h.db")])
    assert res.exit_code == 2 and "no test results" in res.output
    bad = tmp_path / "bad.xml"
    bad.write_text("<not xml")
    res = runner.invoke(app, ["analyze", str(bad), "--db", str(tmp_path / "h.db")])
    assert res.exit_code == 2 and "skipping" in res.output


def test_classify_llm_without_key_is_clean_error(run_dirs, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rep = tmp_path / "r.json"
    ingest_all(run_dirs, tmp_path / "h.db", ["--json-out", str(rep)])
    res = runner.invoke(app, ["classify", str(rep), "--engine", "llm"])
    assert res.exit_code == 2 and "ANTHROPIC_API_KEY" in res.output


def test_quarantine_bad_emit_format(run_dirs, tmp_path):
    rep = tmp_path / "r.json"
    ingest_all(run_dirs, tmp_path / "h.db", ["--json-out", str(rep)])
    res = runner.invoke(
        app, ["quarantine", str(rep), "--file", str(tmp_path / "q.json"), "--emit", "zzz"]
    )
    assert res.exit_code == 2


def test_bundled_sample_end_to_end(tmp_path):
    """The same data the self-test workflow uses."""
    runs = sorted(SAMPLE.glob("run-*"))
    assert len(runs) == 12
    rep = tmp_path / "r.json"
    for r in runs:
        res = runner.invoke(
            app,
            [
                "analyze",
                str(r),
                "--db",
                str(tmp_path / "h.db"),
                "--run-id",
                r.name,
                "--commit",
                (r / "commit.txt").read_text().strip(),
                "--json-out",
                str(rep),
            ],
        )
        assert res.exit_code == 0, res.output
    report = Report.model_validate_json(rep.read_text())
    flaky = [t for t in report.tests if t.metrics.verdict == "flaky"]
    assert len(flaky) >= 8
    assert any(
        t.classification and t.classification.category.value == "stale_element" for t in flaky
    )

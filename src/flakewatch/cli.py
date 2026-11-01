"""Typer CLI: analyze, classify, quarantine, comment."""

from __future__ import annotations

import hashlib
import os
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from . import __version__, github
from . import quarantine as qmod
from .analyzer import DEFAULT_THRESHOLD, DEFAULT_WINDOW
from .analyzer import analyze as run_analysis
from .classify import (
    AnthropicClient,
    Classifier,
    HeuristicClassifier,
    LLMClassifier,
    MockLLMClient,
    evidence_for,
)
from .models import CaseResult, Report, RunInfo
from .parser import merge_attempts, parse_junit
from .report import load_report, render_markdown, to_json
from .store import HistoryStore

app = typer.Typer(
    help="Detect flaky tests across CI runs and classify their probable root cause.",
    no_args_is_help=True,
    add_completion=False,
)


class Engine(str, Enum):
    none = "none"
    heuristic = "heuristic"
    llm = "llm"
    mock_llm = "mock-llm"


def make_classifier(engine: Engine) -> Classifier | None:
    if engine == Engine.none:
        return None
    if engine == Engine.heuristic:
        return HeuristicClassifier()
    if engine == Engine.mock_llm:
        return LLMClassifier(MockLLMClient())
    return LLMClassifier(AnthropicClient())


def classify_report(report: Report, engine: Engine) -> Report:
    clf = make_classifier(engine)
    if clf is None:
        return report
    for t in report.tests:
        if t.metrics.verdict == "flaky":
            t.classification = clf.classify(evidence_for(t))
    report.classify_engine = clf.name
    return report


def _expand(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(p.rglob("*.xml")))
        elif p.exists():
            files.append(p)
        else:
            typer.echo(f"warning: {p} does not exist", err=True)
    return files


def _default_run_id(files: list[Path]) -> str:
    gh = os.environ.get("GITHUB_RUN_ID")
    if gh:
        return f"{gh}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
    h = hashlib.sha256()
    for f in files:
        h.update(f.read_bytes())
    return "local-" + h.hexdigest()[:12]


def _fail(msg: str, code: int = 2) -> typer.Exit:
    typer.echo(f"error: {msg}", err=True)
    return typer.Exit(code)


@app.callback(invoke_without_command=True)
def _main(
    version: Annotated[bool, typer.Option("--version", help="Print version and exit.")] = False,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def analyze(
    paths: Annotated[
        list[Path] | None, typer.Argument(help="JUnit XML files or directories (recursive).")
    ] = None,
    db: Annotated[Path, typer.Option(help="SQLite history file.")] = Path(".flakewatch/history.db"),
    run_id: Annotated[str | None, typer.Option(help="Defaults to GITHUB_RUN_ID-attempt.")] = None,
    commit: Annotated[str | None, typer.Option(help="Defaults to GITHUB_SHA.")] = None,
    timestamp: Annotated[float | None, typer.Option(help="Epoch seconds for this run.")] = None,
    window: Annotated[int, typer.Option(help="Analyse the most recent N runs.")] = DEFAULT_WINDOW,
    keep_runs: Annotated[int, typer.Option(help="Prune history beyond N runs.")] = 200,
    threshold: Annotated[float, typer.Option(help="Min score to call a test flaky.")] = (
        DEFAULT_THRESHOLD
    ),
    engine: Annotated[Engine, typer.Option(help="Root-cause classifier.")] = Engine.heuristic,
    mock_llm: Annotated[
        bool, typer.Option("--mock-llm", help="Shortcut for --engine mock-llm.")
    ] = False,
    json_out: Annotated[Path | None, typer.Option(help="Write JSON report here.")] = None,
    md_out: Annotated[Path | None, typer.Option(help="Write Markdown report here.")] = None,
    quarantine_file: Annotated[
        Path | None,
        typer.Option(help="Quarantine file (shown in report; used by --fail-on-flaky)."),
    ] = None,
    summary: Annotated[bool, typer.Option(help="Append Markdown to $GITHUB_STEP_SUMMARY.")] = False,
    fail_on_flaky: Annotated[
        bool, typer.Option(help="Exit 1 if any flaky test is not quarantined.")
    ] = False,
) -> None:
    """Ingest JUnit XML into the history DB, then compute flakiness over recent runs."""
    store = HistoryStore(db)
    try:
        if paths:
            files = _expand(paths)
            results: list[CaseResult] = []
            stamps: list[float] = []
            for f in files:
                try:
                    res, ts = parse_junit(f)
                except Exception as exc:  # noqa: BLE001
                    typer.echo(f"warning: skipping {f}: {type(exc).__name__}", err=True)
                    continue
                results.extend(res)
                if ts is not None:
                    stamps.append(ts)
            if not results:
                raise _fail("no test results found in the given paths")
            run = RunInfo(
                run_id=run_id or _default_run_id(files),
                commit_sha=commit or os.environ.get("GITHUB_SHA"),
                timestamp=timestamp or (min(stamps) if stamps else time.time()),
            )
            store.ingest(run, merge_attempts(results))
            store.prune(keep_runs)
            typer.echo(f"ingested {len(results)} results as run {run.run_id}", err=True)
        report = run_analysis(store, window=window, threshold=threshold)
    finally:
        store.close()
    report = classify_report(report, Engine.mock_llm if mock_llm else engine)
    q = qmod.load(quarantine_file) if quarantine_file else None
    md = render_markdown(report, q)
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(to_json(report), encoding="utf-8")
    if md_out:
        md_out.parent.mkdir(parents=True, exist_ok=True)
        md_out.write_text(md, encoding="utf-8")
    if summary:
        github.write_job_summary(md)
    if not (json_out or md_out or summary):
        sys.stdout.write(md)
    flaky = [t for t in report.tests if t.metrics.verdict == "flaky"]
    typer.echo(
        f"{len(flaky)} flaky / {report.totals.get('tests', 0)} tests over "
        f"{report.window_runs} run(s)",
        err=True,
    )
    if fail_on_flaky:
        active = {e.test_id for e in q.entries if qmod.is_active(e)} if q else set()
        if any(t.test_id not in active for t in flaky):
            raise typer.Exit(1)


@app.command()
def classify(
    report_path: Annotated[Path, typer.Argument(help="JSON report from `analyze`.", exists=True)],
    engine: Annotated[Engine, typer.Option(help="Classifier to run.")] = Engine.heuristic,
    mock_llm: Annotated[
        bool, typer.Option("--mock-llm", help="Shortcut for --engine mock-llm.")
    ] = False,
    out: Annotated[
        Path | None, typer.Option(help="Output path (default: overwrite input).")
    ] = None,
) -> None:
    """(Re)classify the flaky tests in a JSON report."""
    report = load_report(report_path)
    try:
        report = classify_report(report, Engine.mock_llm if mock_llm else engine)
    except RuntimeError as exc:
        raise _fail(str(exc)) from None
    (out or report_path).write_text(to_json(report), encoding="utf-8")
    n = sum(1 for t in report.tests if t.classification)
    typer.echo(f"classified {n} test(s) with {report.classify_engine}", err=True)


@app.command()
def quarantine(
    report_path: Annotated[Path, typer.Argument(help="JSON report from `analyze`.", exists=True)],
    file: Annotated[Path, typer.Option(help="Quarantine file to create/update.")] = Path(
        ".flakewatch/quarantine.json"
    ),
    ttl_days: Annotated[int, typer.Option(min=1, help="Days until an entry expires.")] = 14,
    min_score: Annotated[
        float, typer.Option(help="Only quarantine tests at/above this score.")
    ] = 0.3,
    emit: Annotated[
        str | None, typer.Option(help="Print active entries as: pytest | surefire | ids.")
    ] = None,
    today: Annotated[str | None, typer.Option(help="YYYY-MM-DD override (testing).")] = None,
) -> None:
    """Add/renew flaky tests in the quarantine file (with TTL) and drop expired entries."""
    now = datetime.strptime(today, qmod.DATE_FMT).replace(tzinfo=timezone.utc) if today else None
    report = load_report(report_path)
    q, changes = qmod.update(qmod.load(file), report, ttl_days, min_score, now)
    qmod.save(q, file)
    typer.echo(
        f"quarantine: +{len(changes['added'])} added, {len(changes['renewed'])} renewed, "
        f"{len(changes['expired'])} expired -> {len(q.entries)} active ({file})",
        err=True,
    )
    if emit:
        try:
            typer.echo(qmod.emit(q, emit, now))
        except ValueError as exc:
            raise _fail(str(exc)) from None


@app.command()
def comment(
    report_path: Annotated[Path, typer.Argument(help="JSON report from `analyze`.", exists=True)],
    quarantine_file: Annotated[
        Path | None, typer.Option(help="Quarantine file to mention.")
    ] = None,
    out: Annotated[Path | None, typer.Option(help="Write Markdown here (default: stdout).")] = None,
    summary: Annotated[bool, typer.Option(help="Append to $GITHUB_STEP_SUMMARY.")] = False,
    post: Annotated[bool, typer.Option(help="Post/update a sticky PR comment.")] = False,
    repo: Annotated[
        str | None, typer.Option(help="owner/name (default: GITHUB_REPOSITORY).")
    ] = None,
    pr: Annotated[int | None, typer.Option(help="PR number (default: from event payload).")] = None,
) -> None:
    """Render the Markdown report; optionally write the job summary and/or post a PR comment."""
    report = load_report(report_path)
    q = qmod.load(quarantine_file) if quarantine_file else None
    md = render_markdown(report, q)
    if out:
        out.write_text(md, encoding="utf-8")
    elif not (summary or post):
        sys.stdout.write(md)
    if summary and not github.write_job_summary(md):
        typer.echo("warning: GITHUB_STEP_SUMMARY not set", err=True)
    if post:
        token = os.environ.get("GITHUB_TOKEN", "")
        repo = repo or os.environ.get("GITHUB_REPOSITORY")
        pr = pr or github.pr_number_from_event()
        if not (token and repo and pr):
            typer.echo("warning: --post needs GITHUB_TOKEN, repo and PR number; skipped", err=True)
            return
        try:
            typer.echo(f"PR comment {github.post_or_update_comment(repo, pr, md, token)}", err=True)
        except Exception as exc:  # noqa: BLE001 - fork PRs have read-only tokens; don't fail CI
            typer.echo(f"warning: could not post PR comment ({type(exc).__name__})", err=True)

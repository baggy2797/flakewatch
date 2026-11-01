from __future__ import annotations

import io
import json

import pytest
from typer.testing import CliRunner

from flakewatch import github
from flakewatch.cli import app
from flakewatch.report import MARKER

from .test_cli import ingest_all, run_dirs  # noqa: F401


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_summary_without_env_returns_false(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert github.write_job_summary("x") is False


def test_pr_number_from_event(tmp_path, monkeypatch):
    ev = tmp_path / "e.json"
    ev.write_text(json.dumps({"pull_request": {"number": 42}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(ev))
    assert github.pr_number_from_event() == 42
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "none"))
    assert github.pr_number_from_event() is None
    monkeypatch.delenv("GITHUB_EVENT_PATH")
    assert github.pr_number_from_event() is None


@pytest.mark.parametrize(
    "existing,verb,methods",
    [
        ([], "created", ["GET", "POST"]),
        ([{"id": 9, "body": f"{MARKER} old"}], "updated", ["GET", "PATCH"]),
    ],
)
def test_post_or_update_comment(monkeypatch, existing, verb, methods):
    calls = []

    def fake(req, timeout):
        calls.append((req.get_method(), req.full_url, dict(req.header_items())))
        return _Resp(json.dumps(existing if req.get_method() == "GET" else {}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert github.post_or_update_comment("o/r", 7, "body", "tok") == verb
    assert [c[0] for c in calls] == methods
    assert calls[0][2]["Authorization"] == "Bearer tok"
    if verb == "updated":
        assert calls[1][1].endswith("/issues/comments/9")


def test_refuses_non_github_url():
    with pytest.raises(ValueError):
        github._call("GET", "https://evil.example/x", "t")


def test_cli_post_paths(run_dirs, tmp_path, monkeypatch, capsys):  # noqa: F811
    runner = CliRunner()
    rep = tmp_path / "r.json"
    ingest_all(run_dirs, tmp_path / "h.db", ["--json-out", str(rep)])
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    res = runner.invoke(app, ["comment", str(rep), "--post"])
    assert "skipped" in res.output

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: _Resp(b"[]"))
    res = runner.invoke(app, ["comment", str(rep), "--post", "--repo", "o/r", "--pr", "3"])
    assert "PR comment created" in res.output

    def boom(req, timeout):
        raise OSError("403")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    res = runner.invoke(app, ["comment", str(rep), "--post", "--repo", "o/r", "--pr", "3"])
    assert res.exit_code == 0 and "could not post" in res.output

    summ = tmp_path / "s.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summ))
    res = runner.invoke(app, ["comment", str(rep), "--summary", "--out", str(tmp_path / "c.md")])
    assert summ.read_text().startswith(MARKER)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY")
    res = runner.invoke(app, ["comment", str(rep), "--summary"])
    assert "GITHUB_STEP_SUMMARY not set" in res.output

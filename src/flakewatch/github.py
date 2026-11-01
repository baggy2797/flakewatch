"""GitHub integration: job summary and sticky PR comment (stdlib HTTP, token from env)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .report import MARKER

API = "https://api.github.com"


def write_job_summary(markdown: str) -> bool:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return False
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(markdown + "\n")
    return True


def pr_number_from_event() -> int | None:
    event = os.environ.get("GITHUB_EVENT_PATH")
    if not event or not Path(event).exists():
        return None
    data = json.loads(Path(event).read_text(encoding="utf-8"))
    num = data.get("pull_request", {}).get("number") or data.get("number")
    return int(num) if isinstance(num, int) else None


def _call(method: str, url: str, token: str, body: dict[str, str] | None = None) -> object:
    if not url.startswith(API + "/"):
        raise ValueError("refusing non-GitHub URL")
    req = urllib.request.Request(  # noqa: S310 - scheme/host checked above
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
        raw = resp.read()
    return json.loads(raw) if raw else None


def post_or_update_comment(repo: str, pr: int, markdown: str, token: str) -> str:
    """Create the flakewatch comment, or update the existing one (found by MARKER)."""
    base = f"{API}/repos/{repo}/issues"
    existing = _call("GET", f"{base}/{pr}/comments?per_page=100", token)
    if isinstance(existing, list):
        for c in existing:
            if isinstance(c, dict) and MARKER in str(c.get("body", "")):
                _call("PATCH", f"{base}/comments/{c['id']}", token, {"body": markdown})
                return "updated"
    _call("POST", f"{base}/{pr}/comments", token, {"body": markdown})
    return "created"

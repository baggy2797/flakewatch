"""Failure-signature normalisation: collapse volatile details so equal failures cluster."""

from __future__ import annotations

import hashlib
import re

_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\(Session info:.*?\)", re.S), ""),
    (re.compile(r"\bat\s+0x[0-9a-fA-F]+"), "at <hex>"),
    (
        re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
        "<uuid>",
    ),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<hex>"),
    (re.compile(r"\b[0-9a-f]{16,}\b", re.I), "<hex>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?"), "<ts>"),
    (re.compile(r"\"[^\"\n]{0,200}\""), '"<s>"'),
    (re.compile(r"'[^'\n]{0,200}'"), "'<s>'"),
    (re.compile(r"\d+"), "N"),
    (re.compile(r"\s+"), " "),
]
_FRAME = re.compile(r"(?:File \"[^\"]*?([^/\"]+)\", line \d+, in (\w+))|(?:at ([\w.$]+)\()")
_NOISE_FRAMES = ("selenium", "site-packages", "node_modules", "java.base", "jdk.", "sun.", "pluggy")


def normalize(text: str) -> str:
    for pat, repl in _SUBS:
        text = pat.sub(repl, text)
    return text.strip()


def _top_frame(trace: str) -> str:
    for m in _FRAME.finditer(trace):
        label = f"{m.group(1)}:{m.group(2)}" if m.group(1) else (m.group(3) or "")
        if label and not any(n in label for n in _NOISE_FRAMES):
            return label
    return ""


def signature(exc_type: str | None, message: str | None, trace: str | None) -> str:
    """Stable 10-hex-char signature of a failure."""
    first_line = (message or "").strip().splitlines()[0] if (message or "").strip() else ""
    body = f"{normalize(exc_type or '')}|{normalize(first_line)[:200]}|{_top_frame(trace or '')}"
    return hashlib.sha1(body.encode(), usedforsecurity=False).hexdigest()[:10]  # noqa: S324

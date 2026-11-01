"""Classifier interface and the evidence handed to every classifier."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from ..models import Classification, FlakyTest


class Evidence(BaseModel):
    """What a classifier is allowed to see about one flaky test."""

    test_id: str
    exc_type: str = ""
    message: str = ""
    trace: str = ""
    other_messages: list[str] = Field(default_factory=list)
    flip_rate: float = 0.0
    retry_pass_runs: int = 0
    framework: str = "unknown"

    @property
    def text(self) -> str:
        return "\n".join([self.exc_type, self.message, self.trace, *self.other_messages])


def evidence_for(test: FlakyTest) -> Evidence:
    sigs = test.signatures
    top = sigs[0] if sigs else None
    return Evidence(
        test_id=test.test_id,
        exc_type=top.exc_type if top else "",
        message=top.message if top else "",
        trace=top.trace if top else "",
        other_messages=[s.message for s in sigs[1:]],
        flip_rate=test.metrics.flip_rate,
        retry_pass_runs=test.metrics.retry_pass_runs,
        framework=test.framework,
    )


class Classifier(Protocol):
    name: str

    def classify(self, ev: Evidence) -> Classification: ...

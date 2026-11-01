"""Pydantic models shared by the parser, store, analyzer, classifiers and reports."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Cause(str, Enum):
    """Probable root-cause taxonomy."""

    TIMING_WAIT = "timing_wait"
    STALE_ELEMENT = "stale_element"
    ORDER_DEPENDENCE = "order_dependence"
    SHARED_STATE = "shared_state"
    NETWORK_ENV = "network_env"
    DATA = "data"
    UNKNOWN = "unknown"


class CaseResult(BaseModel):
    """Final outcome of one test in one CI run (after merging retries/shards)."""

    test_id: str
    status: Status
    duration: float = 0.0
    attempts: int = 1
    retried_pass: bool = False
    fail_type: str | None = None
    fail_message: str | None = None
    fail_trace: str | None = None
    framework: str = "unknown"


class RunInfo(BaseModel):
    run_id: str
    commit_sha: str | None = None
    timestamp: float


class Classification(BaseModel):
    category: Cause
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    evidence: list[str] = Field(default_factory=list)
    engine: str = "heuristic"


class SignatureStat(BaseModel):
    signature: str
    count: int
    exc_type: str
    message: str
    trace: str = ""


class Metrics(BaseModel):
    runs: int
    passes: int
    failures: int
    fail_rate: float
    flips: int
    flip_rate: float
    retry_pass_runs: int
    same_commit_mixed: bool
    score: float
    verdict: str  # flaky | broken | stable | insufficient


class FlakyTest(BaseModel):
    test_id: str
    framework: str = "unknown"
    metrics: Metrics
    signatures: list[SignatureStat] = Field(default_factory=list)
    classification: Classification | None = None


class Cluster(BaseModel):
    signature: str
    exc_type: str
    message: str
    tests: list[str]
    occurrences: int


class Report(BaseModel):
    schema_version: int = 1
    generated_at: str
    window_runs: int
    run_ids: list[str]
    totals: dict[str, int]
    threshold: float
    tests: list[FlakyTest]
    clusters: list[Cluster] = Field(default_factory=list)
    classify_engine: str | None = None


class QuarantineEntry(BaseModel):
    test_id: str
    added: str
    expires: str
    reason: str = ""
    category: str = "unknown"
    score: float = 0.0
    renewals: int = 0


class QuarantineFile(BaseModel):
    version: int = 1
    entries: list[QuarantineEntry] = Field(default_factory=list)

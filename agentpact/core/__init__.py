"""Core types and models for agentpact."""

from agentpact.core.enums import ClauseKind, EventKind, OnFail, Severity
from agentpact.core.errors import ContractLoadError, SessionError, ViolationError
from agentpact.core.models import (
    Clause,
    Event,
    PredicateResult,
    SessionState,
    SessionSummary,
    Violation,
)

__all__ = [
    "ClauseKind", "EventKind", "OnFail", "Severity",
    "ContractLoadError", "SessionError", "ViolationError",
    "Clause", "Event", "PredicateResult", "SessionState", "SessionSummary", "Violation",
]

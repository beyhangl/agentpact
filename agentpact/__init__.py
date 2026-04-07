"""agentpact — Agent Behavioral Contracts.

Design-by-Contract for AI agents. Declare what agents must/must not do,
enforce at runtime, detect behavioral drift, generate compliance docs.
"""

__version__ = "0.1.0"

from agentpact.core.enums import ClauseKind, EventKind, OnFail, Severity
from agentpact.core.errors import ContractLoadError, ViolationError
from agentpact.core.models import (
    Clause, Event, PredicateResult, SessionState, SessionSummary, Violation,
)
from agentpact.contract import Contract
from agentpact.session import Session, get_active_session
from agentpact.predicates.base import predicate, get_predicate, list_predicates

__all__ = [
    "ClauseKind", "EventKind", "OnFail", "Severity",
    "ContractLoadError", "ViolationError",
    "Clause", "Event", "PredicateResult", "SessionState", "SessionSummary", "Violation",
    "Contract", "Session", "get_active_session",
    "predicate", "get_predicate", "list_predicates",
]

"""Predicate system — registry, base types, and all built-in predicates."""

from agentpact.predicates.base import predicate, get_predicate, list_predicates

# Import all built-in predicates to register them
from agentpact.predicates.cost import cost_under, cost_per_turn_under, token_budget
from agentpact.predicates.tools import must_call, must_not_call, tool_order, tools_allowed, max_tool_calls
from agentpact.predicates.output import no_pii, output_contains, output_matches, max_output_length, output_must_not_contain
from agentpact.predicates.timing import max_latency, session_timeout, max_turns
from agentpact.predicates.behavioral import no_loops, max_retries, drift_bounds, no_repeated_output

__all__ = [
    "predicate", "get_predicate", "list_predicates",
    # Cost
    "cost_under", "cost_per_turn_under", "token_budget",
    # Tools
    "must_call", "must_not_call", "tool_order", "tools_allowed", "max_tool_calls",
    # Output
    "no_pii", "output_contains", "output_matches", "max_output_length", "output_must_not_contain",
    # Timing
    "max_latency", "session_timeout", "max_turns",
    # Behavioral
    "no_loops", "max_retries", "drift_bounds", "no_repeated_output",
]

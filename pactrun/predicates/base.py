"""Predicate registration system.

Predicates are factory functions that return a checker function.
The checker takes (Event, SessionState) and returns PredicateResult.

Usage::

    @predicate("cost_under", owasp=("ASI08",))
    def cost_under(max_usd: float):
        def check(event, state):
            return PredicateResult(
                passed=state.total_cost_usd <= max_usd,
                expected=f"<= ${max_usd:.4f}",
                actual=f"${state.total_cost_usd:.4f}",
            )
        return check
"""

from __future__ import annotations

from collections.abc import Callable

from pactrun.core.models import Event, PredicateResult, SessionState

# Global registry: name → factory function
_PREDICATE_REGISTRY: dict[str, Callable[..., Callable[[Event, SessionState], PredicateResult]]] = {}

# name → tuple of OWASP Agentic risk IDs the predicate contributes coverage for.
_PREDICATE_OWASP: dict[str, tuple[str, ...]] = {}

# OWASP Top 10 for Agentic Applications (2026). Titles are the published ones;
# a predicate tagged with an ID provides *partial, runtime* mitigation for that
# risk — it is a control, not a certification of coverage.
OWASP_AGENTIC_2026: dict[str, str] = {
    "ASI01": "Agent Goal Hijack",
    "ASI02": "Tool Misuse & Exploitation",
    "ASI03": "Identity & Privilege Abuse",
    "ASI04": "Agentic Supply Chain Vulnerabilities",
    "ASI05": "Unexpected Code Execution (RCE)",
    "ASI06": "Memory & Context Poisoning",
    "ASI07": "Insecure Inter-Agent Communication",
    "ASI08": "Cascading Failures",
    "ASI09": "Human-Agent Trust Exploitation",
    "ASI10": "Rogue Agents",
}


def predicate(name: str, owasp: tuple[str, ...] | list[str] = ()) -> Callable:
    """Decorator to register a predicate factory function.

    The decorated function should accept configuration args and return
    a checker function ``(Event, SessionState) -> PredicateResult``.

    ``owasp`` optionally tags the predicate with the OWASP Agentic risk IDs
    (``ASI01``..``ASI10``) it helps mitigate, surfaced by ``pactrun predicates``
    and :func:`owasp_coverage`.
    """
    ids = tuple(owasp)
    unknown = [i for i in ids if i not in OWASP_AGENTIC_2026]
    if unknown:
        raise ValueError(f"predicate({name!r}): unknown OWASP ids {unknown}")

    def decorator(fn: Callable) -> Callable:
        _PREDICATE_REGISTRY[name] = fn
        fn.predicate_name = name  # type: ignore[attr-defined]
        if ids:
            _PREDICATE_OWASP[name] = ids
            fn.owasp = ids  # type: ignore[attr-defined]
        return fn
    return decorator


def predicate_owasp(name: str) -> tuple[str, ...]:
    """Return the OWASP Agentic risk IDs a registered predicate is tagged with."""
    return _PREDICATE_OWASP.get(name, ())


def owasp_coverage() -> dict[str, list[str]]:
    """Map each OWASP Agentic risk ID to the predicates that help mitigate it.

    Every ID is present; an empty list means pactrun ships no runtime control
    for that risk (by design — some are deployment/supply-chain concerns a
    contract library cannot observe).
    """
    coverage: dict[str, list[str]] = {rid: [] for rid in OWASP_AGENTIC_2026}
    for pred_name, ids in _PREDICATE_OWASP.items():
        for rid in ids:
            coverage[rid].append(pred_name)
    return {rid: sorted(names) for rid, names in coverage.items()}


def get_predicate(name: str) -> Callable:
    """Look up a predicate factory by name.

    Raises KeyError if the predicate is not registered.
    """
    if name not in _PREDICATE_REGISTRY:
        raise KeyError(
            f"Unknown predicate: {name!r}. "
            f"Available: {sorted(_PREDICATE_REGISTRY.keys())}"
        )
    return _PREDICATE_REGISTRY[name]


def list_predicates() -> list[str]:
    """Return sorted list of all registered predicate names."""
    return sorted(_PREDICATE_REGISTRY.keys())

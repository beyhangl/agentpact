"""Behavioral predicates — detect loops, drift, and repetition."""

from __future__ import annotations

from pactrun.core.enums import EventKind
from pactrun.core.models import Event, PredicateResult, SessionState
from pactrun.predicates.base import predicate


@predicate("no_loops")
def no_loops(window: int = 5, threshold: float = 0.8):
    """Detect repetitive tool call patterns (probable infinite loops).

    Checks if the last `window` tool calls have >threshold fraction
    of identical calls.
    """
    def check(event: Event, state: SessionState) -> PredicateResult:
        history = state.tool_call_history
        if len(history) < window:
            return PredicateResult(passed=True)
        recent = history[-window:]
        if not recent:
            return PredicateResult(passed=True)
        most_common_count = max(recent.count(t) for t in set(recent))
        ratio = most_common_count / len(recent)
        return PredicateResult(
            passed=ratio < threshold,
            expected=f"loop ratio < {threshold:.0%}",
            actual=f"{ratio:.0%} repetition in last {window} calls",
            message=f"Possible loop: {ratio:.0%} of last {window} tool calls are identical",
        )
    check.predicate_name = "no_loops"  # type: ignore[attr-defined]
    return check


@predicate("max_retries")
def max_retries(n: int, tool: str | None = None):
    """Max N consecutive calls to the same tool (or a specific tool)."""
    def check(event: Event, state: SessionState) -> PredicateResult:
        history = state.tool_call_history
        if len(history) < 2:
            return PredicateResult(passed=True)

        # Count consecutive identical calls at the end
        target = tool or (history[-1] if history else None)
        if target is None:
            return PredicateResult(passed=True)

        consecutive = 0
        for t in reversed(history):
            if t == target:
                consecutive += 1
            else:
                break

        return PredicateResult(
            passed=consecutive <= n,
            expected=f"<= {n} consecutive '{target}' calls",
            actual=f"{consecutive} consecutive calls",
            message=f"Tool '{target}' called {consecutive} times consecutively (max {n})",
        )
    check.predicate_name = "max_retries"  # type: ignore[attr-defined]
    return check


@predicate("drift_bounds")
def drift_bounds(cost_pct: float | None = None, tokens_pct: float | None = None):
    """Per-turn metrics must stay within N% of session average.

    Detects gradual drift by comparing the latest turn's metrics
    against the running average.
    """
    def check(event: Event, state: SessionState) -> PredicateResult:
        # Need at least 3 turns to detect drift
        if len(state.cost_per_turn) < 3:
            return PredicateResult(passed=True)

        violations: list[str] = []

        if cost_pct is not None and state.cost_per_turn:
            avg = sum(state.cost_per_turn) / len(state.cost_per_turn)
            if avg > 0:
                latest = state.cost_per_turn[-1]
                deviation = (latest - avg) / avg
                if deviation > cost_pct:
                    violations.append(f"cost drift {deviation:+.0%} (limit {cost_pct:+.0%})")

        if tokens_pct is not None and state.tokens_per_turn:
            avg = sum(state.tokens_per_turn) / len(state.tokens_per_turn)
            if avg > 0:
                latest = state.tokens_per_turn[-1]
                deviation = (latest - avg) / avg
                if deviation > tokens_pct:
                    violations.append(f"token drift {deviation:+.0%} (limit {tokens_pct:+.0%})")

        if violations:
            return PredicateResult(
                passed=False,
                message="Drift detected: " + "; ".join(violations),
            )
        return PredicateResult(passed=True)
    check.predicate_name = "drift_bounds"  # type: ignore[attr-defined]
    return check


@predicate("no_repeated_output")
def no_repeated_output(window: int = 3):
    """Agent must not produce identical outputs across recent turns."""
    def check(event: Event, state: SessionState) -> PredicateResult:
        history = state.output_history
        if len(history) < 2:
            return PredicateResult(passed=True)
        recent = history[-window:]
        if len(recent) != len(set(recent)):
            return PredicateResult(
                passed=False,
                message=f"Repeated output detected in last {window} turns",
            )
        return PredicateResult(passed=True)
    check.predicate_name = "no_repeated_output"  # type: ignore[attr-defined]
    return check


def _is_tool_error(e: Event) -> bool:
    """Classify a tool-call event as failed across the shapes adapters populate."""
    if e.error is not None:
        return True
    meta = e.metadata or {}
    if meta.get("is_error") or meta.get("isError"):  # MCP-style result flag
        return True
    if isinstance(e.tool_result, BaseException):
        return True
    return False


@predicate("tool_error_rate_under")
def tool_error_rate_under(max_rate: float = 0.3, window: int = 10, min_calls: int = 3):
    """Rolling tool-failure fraction must stay under a ceiling.

    Looks at the last ``window`` tool calls; if at least ``min_calls`` have
    occurred, fails when the failed fraction exceeds ``max_rate`` (a degraded-
    grounding signal: the agent keeps calling tools that error). Below
    ``min_calls`` it passes (warm-up). A call is "failed" when ``Event.error``
    is set, its ``metadata`` carries an ``is_error`` / ``isError`` flag (MCP
    shape), or its ``tool_result`` is an exception.

    Note: fires only where the adapter populates an error signal (the manual and
    MCP adapters today). It degrades safely — an unflagged call counts as a
    success — so it never false-positives on adapters that don't yet map tool
    errors into ``Event.error``.
    """
    def check(event: Event, state: SessionState) -> PredicateResult:
        tool_events = [e for e in state.events if e.kind == EventKind.TOOL_CALL]
        recent = tool_events[-window:]
        if len(recent) < min_calls:
            return PredicateResult(passed=True)
        errors = sum(1 for e in recent if _is_tool_error(e))
        rate = errors / len(recent)
        return PredicateResult(
            passed=rate <= max_rate,
            expected=f"tool error rate <= {max_rate:.0%}",
            actual=f"{rate:.0%} ({errors}/{len(recent)})",
            message=f"Tool error rate {rate:.0%} ({errors}/{len(recent)}) exceeds {max_rate:.0%}",
        )
    check.predicate_name = "tool_error_rate_under"  # type: ignore[attr-defined]
    return check


def _arg_fingerprint(tool_name, tool_args, key_fields=None, ignore_fields=None) -> str:
    """Stable identity for a tool call over a chosen subset of its arguments."""
    import json

    args = dict(tool_args or {})
    if key_fields is not None:
        subset = {k: args[k] for k in key_fields if k in args}
    else:
        subset = args
        for k in (ignore_fields or []):
            subset.pop(k, None)
    try:
        blob = json.dumps(subset, sort_keys=True, default=str)
    except (TypeError, ValueError):
        blob = str(sorted((str(k), str(v)) for k, v in subset.items()))
    return f"{tool_name}\x00{blob}"


@predicate("bounded_error_retries")
def bounded_error_retries(
    max_transient: int = 3,
    max_permanent: int = 0,
    retryable=(r"timeout", r"rate.?limit", r"5\d\d", r"connection"),
    permanent=(r"401", r"403", r"invalid", r"unauthorized", r"not.?found"),
    status_key: str = "status_code",
):
    """Cap consecutive retries of a failing tool by error class.

    Not all failures are worth retrying: a timeout or ``5xx`` may clear on retry
    (transient), but a ``401``/``403``/invalid-argument won't (permanent). This
    counts the current tail-run of consecutive errors for the *same tool* and
    fails when a permanent error exceeds ``max_permanent`` (default 0 — stop
    immediately) or a transient run exceeds ``max_transient``. A success for that
    tool resets the streak. Classification matches ``retryable`` / ``permanent``
    regexes (case-insensitive) against the error text plus ``metadata[status_key]``;
    **permanent wins on ambiguity**, and an unrecognized error is treated as
    transient. Route with ``on_fail="escalate"``.
    """
    import re

    perm_rx = [re.compile(p, re.IGNORECASE) for p in permanent]
    trans_rx = [re.compile(p, re.IGNORECASE) for p in retryable]

    def _classify(e: Event) -> str:
        text = f"{e.error or ''} {(e.metadata or {}).get(status_key, '')}"
        if any(rx.search(text) for rx in perm_rx):
            return "permanent"
        if any(rx.search(text) for rx in trans_rx):
            return "transient"
        return "transient"

    def check(event: Event, state: SessionState) -> PredicateResult:
        if event.kind != EventKind.TOOL_CALL or not _is_tool_error(event):
            return PredicateResult(passed=True)
        tool = event.tool_name
        streak = []
        for e in reversed(state.events):
            if e.kind != EventKind.TOOL_CALL or e.tool_name != tool:
                continue
            if _is_tool_error(e):
                streak.append(e)
            else:
                break  # a success for this tool ends the run
        perm = sum(1 for e in streak if _classify(e) == "permanent")
        if perm > max_permanent:
            return PredicateResult(
                passed=False,
                expected=f"<= {max_permanent} permanent-error retries of '{tool}'",
                actual=f"{perm} permanent error(s)",
                message=f"Tool '{tool}' hit {perm} permanent error(s) (max {max_permanent}) — retrying won't help",
            )
        if len(streak) > max_transient:
            return PredicateResult(
                passed=False,
                expected=f"<= {max_transient} consecutive retries of '{tool}'",
                actual=f"{len(streak)} consecutive errors",
                message=f"Tool '{tool}' failed {len(streak)} times in a row (max {max_transient})",
            )
        return PredicateResult(passed=True)
    check.predicate_name = "bounded_error_retries"  # type: ignore[attr-defined]
    return check


@predicate("no_redundant_reads")
def no_redundant_reads(tools=("read_file", "search"), max_repeats: int = 1, args_keys=None):
    """Flag the same read repeated past a threshold (wasted tokens/latency).

    Keys each call to a listed tool on ``(tool_name, canonical args)`` and fails
    when the identical read has occurred more than ``max_repeats`` extra times —
    i.e. with ``max_repeats=1`` the *third* identical read fails (one original +
    one allowed repeat). ``args_keys`` restricts the identity to those argument
    keys so volatile fields (a request id, a cursor) don't defeat it.
    """
    tools_set = set(tools)

    def check(event: Event, state: SessionState) -> PredicateResult:
        if event.kind != EventKind.TOOL_CALL or event.tool_name not in tools_set:
            return PredicateResult(passed=True)
        fp = _arg_fingerprint(event.tool_name, event.tool_args, key_fields=args_keys)
        occurrences = sum(
            1 for e in state.events
            if e.kind == EventKind.TOOL_CALL and e.tool_name == event.tool_name
            and _arg_fingerprint(e.tool_name, e.tool_args, key_fields=args_keys) == fp
        )
        return PredicateResult(
            passed=occurrences <= max_repeats + 1,
            expected=f"<= {max_repeats} repeat(s) of the same '{event.tool_name}' read",
            actual=f"read #{occurrences}",
            message=f"Redundant read: '{event.tool_name}' with the same arguments called {occurrences} times",
        )
    check.predicate_name = "no_redundant_reads"  # type: ignore[attr-defined]
    return check


@predicate("no_progress_stall")
def no_progress_stall(
    max_turns_without_progress: int = 4,
    max_ms_without_progress: float = 120000,
    max_calls_without_progress=None,
    require_success: bool = True,
    require_new_output: bool = True,
):
    """Fail when the agent stops making progress within a budget.

    "Progress" is a checkpoint event that fires any enabled signal: a **non-error
    tool result** (``require_success``) or a **new distinct output**
    (``require_new_output``). Budgets are measured since the last checkpoint (or
    session start): LLM calls (``max_turns_without_progress``), tool calls
    (``max_calls_without_progress``, off by default), and wall time
    (``max_ms_without_progress``). Set a budget to ``None`` to disable it.

    Catches an agent thrashing on failing tools with *varying* names — which
    ``no_loops`` (name-repetition) and ``max_retries`` (same-name streak) miss.
    Structural, not semantic — pair with ``on_fail="warn"``/``"escalate"``.
    """
    def _is_progress(event: Event, seen: set) -> bool:
        if require_success and event.kind == EventKind.TOOL_CALL and not _is_tool_error(event):
            return True
        if require_new_output and event.output is not None:
            text = str(event.output)
            if text and text not in seen:
                return True
        return False

    def check(event: Event, state: SessionState) -> PredicateResult:
        events = state.events
        seen: set = set()
        anchor_ts = events[0].timestamp if events else event.timestamp
        turns = calls = 0
        for e in events:
            progress = _is_progress(e, seen)
            if e.output is not None:
                t = str(e.output)
                if t:
                    seen.add(t)
            if progress:
                turns = calls = 0
                anchor_ts = e.timestamp
                continue
            if e.kind == EventKind.LLM_CALL:
                turns += 1
            elif e.kind == EventKind.TOOL_CALL:
                calls += 1
        elapsed_ms = (event.timestamp - anchor_ts) * 1000
        if max_turns_without_progress is not None and turns > max_turns_without_progress:
            reason = f"{turns} turns without progress (max {max_turns_without_progress})"
        elif max_calls_without_progress is not None and calls > max_calls_without_progress:
            reason = f"{calls} tool calls without progress (max {max_calls_without_progress})"
        elif max_ms_without_progress is not None and elapsed_ms > max_ms_without_progress:
            reason = f"{elapsed_ms:.0f}ms without progress (max {max_ms_without_progress:.0f}ms)"
        else:
            return PredicateResult(passed=True)
        return PredicateResult(
            passed=False,
            expected="steady progress",
            actual=reason,
            message=f"Agent appears stalled: {reason}",
        )
    check.predicate_name = "no_progress_stall"  # type: ignore[attr-defined]
    return check

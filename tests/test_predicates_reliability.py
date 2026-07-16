"""Tests for bounded_error_retries, no_redundant_reads, no_progress_stall."""

from pactrun import (
    Contract,
    EventKind,
    bounded_error_retries,
    no_loops,
    no_progress_stall,
    no_redundant_reads,
)
from pactrun.core.models import Event


def _tool(name, t, *, error=None, args=None, meta=None, result=None):
    return Event(kind=EventKind.TOOL_CALL, tool_name=name, timestamp=t,
                 error=error, tool_args=args or {}, metadata=meta or {}, tool_result=result)


def _llm(t, output=""):
    return Event(kind=EventKind.LLM_CALL, timestamp=t, output=output)


def _run(pred, events):
    c = Contract("t").require(pred, on_fail="log")
    with c.session() as s:
        for e in events:
            s.record_event(e)
    return s


# ---------------------------------------------------------------------------
# bounded_error_retries
# ---------------------------------------------------------------------------

def test_transient_within_budget_passes():
    events = [_tool("fetch", i, error="timeout") for i in range(3)]  # 3 == max_transient
    assert _run(bounded_error_retries(max_transient=3), events).is_compliant


def test_transient_over_budget_fails():
    events = [_tool("fetch", i, error="connection timeout") for i in range(4)]
    assert not _run(bounded_error_retries(max_transient=3), events).is_compliant


def test_single_permanent_fails_at_zero():
    assert not _run(bounded_error_retries(), [_tool("api", 1, error="HTTP 401 Unauthorized")]).is_compliant


def test_permanent_wins_on_ambiguity():
    # error mentions both a 5xx (transient) and 'invalid' (permanent) -> permanent -> fails at 0
    assert not _run(bounded_error_retries(), [_tool("api", 1, error="503 invalid region")]).is_compliant


def test_status_via_metadata():
    assert not _run(bounded_error_retries(), [_tool("api", 1, error="denied", meta={"status_code": 403})]).is_compliant


def test_unknown_error_treated_transient():
    events = [_tool("x", i, error="weird glitch") for i in range(2)]
    assert _run(bounded_error_retries(max_transient=3), events).is_compliant  # 2 < 3, transient


def test_success_resets_streak():
    events = [_tool("fetch", 1, error="timeout"), _tool("fetch", 2, error="timeout"),
              _tool("fetch", 3), _tool("fetch", 4, error="timeout")]  # success at 3 resets
    assert _run(bounded_error_retries(max_transient=3), events).is_compliant


def test_different_tool_does_not_count():
    events = [_tool("a", 1, error="timeout"), _tool("b", 2, error="timeout"),
              _tool("a", 3, error="timeout"), _tool("b", 4, error="timeout")]
    # per-tool streaks are each 2 -> under budget 3
    assert _run(bounded_error_retries(max_transient=3), events).is_compliant


# ---------------------------------------------------------------------------
# no_redundant_reads
# ---------------------------------------------------------------------------

def test_third_identical_read_fails():
    events = [_tool("read_file", i, args={"path": "/a"}) for i in range(3)]
    assert not _run(no_redundant_reads(max_repeats=1), events).is_compliant


def test_two_identical_reads_pass():
    events = [_tool("read_file", i, args={"path": "/a"}) for i in range(2)]
    assert _run(no_redundant_reads(max_repeats=1), events).is_compliant


def test_distinct_paths_pass():
    events = [_tool("read_file", i, args={"path": f"/{i}"}) for i in range(5)]
    assert _run(no_redundant_reads(max_repeats=1), events).is_compliant


def test_non_listed_tool_ignored():
    events = [_tool("write_file", i, args={"path": "/a"}) for i in range(5)]
    assert _run(no_redundant_reads(tools=("read_file",), max_repeats=1), events).is_compliant


def test_args_keys_ignores_volatile_fields():
    # same path, different request id -> identity on 'path' only catches the repeat
    events = [_tool("search", i, args={"q": "hi", "req_id": i}) for i in range(3)]
    assert not _run(no_redundant_reads(tools=("search",), max_repeats=1, args_keys=["q"]), events).is_compliant


def test_max_repeats_two_boundary():
    events = [_tool("read_file", i, args={"path": "/a"}) for i in range(3)]
    assert _run(no_redundant_reads(max_repeats=2), events).is_compliant  # 3rd ok
    events4 = [_tool("read_file", i, args={"path": "/a"}) for i in range(4)]
    assert not _run(no_redundant_reads(max_repeats=2), events4).is_compliant  # 4th fails


def test_unserializable_args_do_not_raise():
    events = [_tool("read_file", i, args={"path": "/a", "cb": lambda: 1}) for i in range(3)]
    _run(no_redundant_reads(max_repeats=1), events)  # must not raise


# ---------------------------------------------------------------------------
# no_progress_stall
# ---------------------------------------------------------------------------

def test_healthy_run_passes():
    events = [_llm(1, "thinking"), _tool("search", 2, result="ok"),
              _llm(3, "more"), _tool("read", 4, result="data")]
    assert _run(no_progress_stall(), events).is_compliant


def test_varying_name_error_loop_fails_where_no_loops_misses():
    # 4 failing tool calls with DIFFERENT names, no success, no new output
    events = [_tool(f"tool_{i}", i, error="boom") for i in range(4)]
    stall = _run(no_progress_stall(max_calls_without_progress=3, max_turns_without_progress=None,
                                   max_ms_without_progress=None), events)
    assert not stall.is_compliant
    # no_loops sees varying names -> stays compliant on the same trace (the gap)
    assert _run(no_loops(window=3, threshold=0.8), events).is_compliant


def test_repeated_output_past_budget_fails():
    events = [_llm(i, "same answer") for i in range(1, 6)]  # first is new; rest repeat
    assert not _run(no_progress_stall(max_turns_without_progress=2,
                                      max_ms_without_progress=None), events).is_compliant


def test_success_resets_checkpoint():
    events = [_tool(f"t{i}", i, error="boom") for i in range(3)] + [_tool("win", 3, result="ok")] \
        + [_tool(f"u{i}", 4 + i, error="boom") for i in range(2)]
    assert _run(no_progress_stall(max_calls_without_progress=3, max_turns_without_progress=None,
                                  max_ms_without_progress=None), events).is_compliant


def test_ms_budget_via_timestamps():
    events = [_tool("t1", 0.0, error="boom"), _tool("t2", 200.0, error="boom")]  # 200s gap
    assert not _run(no_progress_stall(max_turns_without_progress=None,
                                      max_ms_without_progress=120000), events).is_compliant


def test_warmup_passes():
    events = [_tool("t1", 1, error="boom"), _tool("t2", 2, error="boom")]
    assert _run(no_progress_stall(max_calls_without_progress=3, max_turns_without_progress=None,
                                  max_ms_without_progress=None), events).is_compliant


def test_registered():
    import pactrun
    names = pactrun.list_predicates()
    for n in ("bounded_error_retries", "no_redundant_reads", "no_progress_stall"):
        assert n in names

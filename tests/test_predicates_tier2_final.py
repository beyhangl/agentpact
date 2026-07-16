"""Tests for untrusted_taint_to_sink, ai_disclosure_in_output, approval_request_rate_under."""

import pytest

from pactrun import (
    Contract,
    EventKind,
    ai_disclosure_in_output,
    approval_request_rate_under,
    untrusted_taint_to_sink,
)
from pactrun.core.models import Event


# ---------------------------------------------------------------------------
# untrusted_taint_to_sink
# ---------------------------------------------------------------------------

SECRET = "the launch code is 8827-XYZ-QRESET-9910-DELTA"  # > 24 chars


def _taint_run(pred, ingest_meta, ingest_result, sink_args):
    c = Contract("t").require(pred, on_fail="log")
    with c.session() as s:
        s.emit_tool_call("web_fetch", result=ingest_result, metadata=ingest_meta)
        s.emit_tool_call("send_email", args=sink_args)
    return s


def test_tainted_content_copied_to_sink_blocks():
    s = _taint_run(untrusted_taint_to_sink(), {"untrusted": True}, SECRET,
                   {"body": f"FYI: {SECRET}"})
    assert not s.is_compliant


def test_short_overlap_passes():
    pred = untrusted_taint_to_sink(min_overlap=24)
    s = _taint_run(pred, {"untrusted": True}, "abcdefghij",  # only 10 chars
                   {"body": "abcdefghij and more"})
    assert s.is_compliant


def test_no_prior_taint_passes():
    # ingest not tagged untrusted -> nothing tainted
    s = _taint_run(untrusted_taint_to_sink(), {}, SECRET, {"body": f"FYI: {SECRET}"})
    assert s.is_compliant


def test_unrelated_sink_args_pass():
    s = _taint_run(untrusted_taint_to_sink(), {"untrusted": True}, SECRET,
                   {"body": "Just saying hello, nothing tainted here at all."})
    assert s.is_compliant


def test_sink_arg_keys_scoping():
    pred = untrusted_taint_to_sink(sink_arg_keys=["subject"])
    # tainted content is in 'body', but only 'subject' is checked
    s = _taint_run(pred, {"untrusted": True}, SECRET, {"subject": "hi", "body": SECRET})
    assert s.is_compliant


def test_custom_taint_key():
    pred = untrusted_taint_to_sink(taint_key="tainted")
    s = _taint_run(pred, {"tainted": 1}, SECRET, {"body": SECRET})
    assert not s.is_compliant


def test_non_sink_tool_ignored():
    pred = untrusted_taint_to_sink(sink_tools=("http_post",))
    s = _taint_run(pred, {"untrusted": True}, SECRET, {"body": SECRET})  # send_email not a sink here
    assert s.is_compliant


def test_nested_and_list_args_flattened():
    pred = untrusted_taint_to_sink()
    s = _taint_run(pred, {"untrusted": True}, SECRET,
                   {"payload": {"items": [{"text": SECRET}]}})
    assert not s.is_compliant


def test_min_overlap_below_one_raises():
    with pytest.raises(ValueError):
        untrusted_taint_to_sink(min_overlap=0)


# ---------------------------------------------------------------------------
# ai_disclosure_in_output
# ---------------------------------------------------------------------------

def _disc_run(pred, outputs):
    c = Contract("t").require(pred, on_fail="log")
    with c.session() as s:
        for o in outputs:
            s.emit_llm_response(model="m", output=o)
    return s


def test_first_reply_with_phrase_passes():
    s = _disc_run(ai_disclosure_in_output(), ["Hi, I'm an automated assistant. How can I help?"])
    assert s.is_compliant


def test_first_reply_without_phrase_fails():
    s = _disc_run(ai_disclosure_in_output(), ["Hello there!"])
    assert not s.is_compliant


def test_post_latch_reply_without_phrase_passes_first_only():
    s = _disc_run(ai_disclosure_in_output(first_only=True),
                  ["Hi, I'm an automated assistant.", "Sure, here's the answer."])
    assert s.is_compliant


def test_per_message_mode_fails_later_reply():
    s = _disc_run(ai_disclosure_in_output(first_only=False),
                  ["Hi, I'm an automated assistant.", "Sure, here's the answer."])
    assert not s.is_compliant


def test_fail_closed_on_empty_first_output():
    s = _disc_run(ai_disclosure_in_output(), ["", "I'm an automated assistant now"])
    assert not s.is_compliant  # first reply empty -> fail-closed


def test_match_all():
    pred = ai_disclosure_in_output(must_contain=["automated", "on behalf of Acme"], match="all")
    assert _disc_run(pred, ["I'm automated, writing on behalf of Acme."]).is_compliant
    assert not _disc_run(pred, ["I'm automated."]).is_compliant


def test_pattern_mode():
    pred = ai_disclosure_in_output(must_contain=[r"AI[- ]generated"], pattern=True)
    assert _disc_run(pred, ["These responses are AI-generated."]).is_compliant


def test_non_reply_events_ignored():
    pred = ai_disclosure_in_output()
    c = Contract("t").require(pred, on_fail="log")
    with c.session() as s:
        s.emit_tool_call("search")   # not a reply
        s.emit_llm_response(model="m", output="I'm an automated assistant.")
    assert s.is_compliant


def test_latch_persists_across_run():
    s = _disc_run(ai_disclosure_in_output(),
                  ["I'm an automated assistant.", "answer 1", "answer 2"])
    assert s.is_compliant


def test_bad_match_rejected():
    with pytest.raises(ValueError):
        ai_disclosure_in_output(match="some")


# ---------------------------------------------------------------------------
# approval_request_rate_under
# ---------------------------------------------------------------------------

def _appr(t, tagged=True):
    meta = {"approval_request": True} if tagged else {}
    return Event(kind=EventKind.LLM_CALL, timestamp=t, metadata=meta)


def _rate_run(pred, events):
    c = Contract("t").require(pred, on_fail="log")
    with c.session() as s:
        for e in events:
            s.record_event(e)
    return s


def test_burst_trips():
    events = [_appr(1000.0 + i) for i in range(6)]  # 6 in a tight window
    assert not _rate_run(approval_request_rate_under(max_per_window=5, window_s=300), events).is_compliant


def test_paced_passes():
    events = [_appr(1000.0 + i * 400) for i in range(6)]  # 1 per 400s > 300s window
    assert _rate_run(approval_request_rate_under(max_per_window=5, window_s=300), events).is_compliant


def test_untagged_never_counts():
    events = [_appr(1000.0 + i, tagged=False) for i in range(10)]
    assert _rate_run(approval_request_rate_under(max_per_window=2, window_s=300), events).is_compliant


def test_custom_tag():
    events = [Event(kind=EventKind.LLM_CALL, timestamp=1000.0 + i, metadata={"needs_ok": True}) for i in range(4)]
    pred = approval_request_rate_under(max_per_window=2, window_s=300, approval_tag="needs_ok")
    assert not _rate_run(pred, events).is_compliant


def test_at_cap_boundary_passes():
    events = [_appr(1000.0 + i) for i in range(5)]  # exactly 5 == max
    assert _rate_run(approval_request_rate_under(max_per_window=5, window_s=300), events).is_compliant


def test_registered():
    import pactrun
    names = pactrun.list_predicates()
    for n in ("untrusted_taint_to_sink", "ai_disclosure_in_output", "approval_request_rate_under"):
        assert n in names

"""Tests for no_duplicate_side_effect + its wrap() kwarg."""

from types import SimpleNamespace as NS

from pactrun import Contract, EventKind, no_duplicate_side_effect, wrap
from pactrun.core.models import Event


def _tool(name, t, args):
    return Event(kind=EventKind.TOOL_CALL, tool_name=name, timestamp=t, tool_args=args)


def _run(pred, calls):
    c = Contract("t").require(pred, on_fail="log")
    with c.session() as s:
        for i, (name, args) in enumerate(calls):
            s.record_event(_tool(name, float(i), args))
    return s


def test_identical_send_twice_second_blocked():
    pred = no_duplicate_side_effect("send_email", key_fields=["to", "subject", "body"])
    s = _run(pred, [("send_email", {"to": "a@b.com", "subject": "hi", "body": "x"})] * 2)
    assert len(s.violations) == 1


def test_composite_identity_subject_diff_allowed():
    pred = no_duplicate_side_effect("send_email", key_fields=["to", "subject", "body"])
    s = _run(pred, [
        ("send_email", {"to": "a@b.com", "subject": "hi", "body": "x"}),
        ("send_email", {"to": "a@b.com", "subject": "different", "body": "x"}),
    ])
    assert s.is_compliant


def test_composite_identity_subject_not_in_key_still_blocks():
    pred = no_duplicate_side_effect("send_email", key_fields=["to", "body"])
    s = _run(pred, [
        ("send_email", {"to": "a@b.com", "subject": "hi", "body": "x"}),
        ("send_email", {"to": "a@b.com", "subject": "different", "body": "x"}),
    ])
    assert not s.is_compliant  # subject not part of identity -> duplicate


def test_ignore_fields():
    pred = no_duplicate_side_effect("charge", ignore_fields=["request_id"])
    s = _run(pred, [
        ("charge", {"amount": 100, "request_id": "r1"}),
        ("charge", {"amount": 100, "request_id": "r2"}),
    ])
    assert not s.is_compliant  # request_id ignored -> same identity


def test_retry_token_bump_allowed():
    pred = no_duplicate_side_effect("send", key_fields=["to"], retry_token_field="idempotency_key")
    s = _run(pred, [
        ("send", {"to": "a@b.com", "idempotency_key": "k1"}),
        ("send", {"to": "a@b.com", "idempotency_key": "k2"}),
    ])
    assert s.is_compliant  # different retry token -> intentional new attempt


def test_same_retry_token_blocks():
    pred = no_duplicate_side_effect("send", key_fields=["to"], retry_token_field="idempotency_key")
    s = _run(pred, [
        ("send", {"to": "a@b.com", "idempotency_key": "k1"}),
        ("send", {"to": "a@b.com", "idempotency_key": "k1"}),
    ])
    assert not s.is_compliant


def test_key_fields_none_uses_all_args():
    pred = no_duplicate_side_effect("send")
    s = _run(pred, [("send", {"to": "a", "body": "x"})] * 2)
    assert not s.is_compliant


def test_tool_scoping():
    pred = no_duplicate_side_effect("send")
    s = _run(pred, [("other", {"to": "a"}), ("other", {"to": "a"})])
    assert s.is_compliant


def test_replay_determinism():
    pred = no_duplicate_side_effect("send", key_fields=["to"])
    calls = [("send", {"to": "a@b.com"})] * 2
    s1, s2 = _run(pred, calls), _run(pred, calls)
    assert len(s1.violations) == len(s2.violations) == 1


def test_wrap_kwarg_registers_clause():
    client = NS(chat=NS(completions=NS(create=lambda **kw: None)))
    g = wrap(client, no_duplicate_side_effect={"send_email": ["to", "body"]}, on_violation="log")
    names = {c.predicate_name for c in g._contract.clauses}
    assert "no_duplicate_side_effect" in names


def test_registered():
    import pactrun
    assert "no_duplicate_side_effect" in pactrun.list_predicates()

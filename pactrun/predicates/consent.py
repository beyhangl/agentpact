"""Consent / approval predicates — gate side-effecting tools on signed tokens.

``consent_token_required`` needs a single fresh, action-bound token per call;
``multi_party_approval_required`` needs a quorum of distinct signed approvals
(dual-control). The ``mint_*`` companions produce the tokens host-side.
"""

from __future__ import annotations

from pactrun.core.enums import EventKind
from pactrun.core.models import Event, PredicateResult, SessionState
from pactrun.predicates._signing import _action_sig, _approval_sig
from pactrun.predicates.base import predicate


@predicate("consent_token_required", owasp=("ASI03", "ASI09",))
def consent_token_required(
    tools,
    *,
    token_key: str = "user_consent",
    bind_args: list[str] | None = None,
    max_age_s: float | None = 300,
    secret=None,
):
    """Gate side-effecting tools on a fresh, action-bound consent token.

    Raises the bar from "the model self-authorized" to "the host carried a
    consent token scoped to THIS exact action into the turn". For each call to
    a tool in ``tools``, a token is read from ``event.metadata[token_key]``
    (per-turn), falling back to ``state.metadata[token_key]``. The token is a
    dict ``{"action", "sig", "issued_at"}`` (use :func:`mint_consent_token` to
    produce one). The call passes only if:

    - the token is present;
    - its ``sig`` matches a signature recomputed from the live ``tool_name`` and
      the values of ``bind_args`` — so a token issued for a *different* action
      or different arguments is rejected (no replay);
    - it is fresh: ``time.time() - issued_at <= max_age_s`` (skipped when
      ``max_age_s is None``);
    - if ``secret`` is given, the signature is an HMAC verified with
      ``hmac.compare_digest`` (constant-time).

    Pair with ``on_fail="approve"`` to route a tokenless call to a human, or
    ``on_fail="block"`` to refuse outright. Honest bound: this validates that a
    matching, unexpired, action-bound token was presented; it cannot attest the
    token's origin beyond the shared-secret HMAC the host signs with.
    """
    tools_set = {tools} if isinstance(tools, str) else set(tools)

    def check(event: Event, state: SessionState) -> PredicateResult:
        if event.kind != EventKind.TOOL_CALL or event.tool_name not in tools_set:
            return PredicateResult(passed=True)
        token = (event.metadata or {}).get(token_key)
        if token is None:
            token = (state.metadata or {}).get(token_key)
        if not isinstance(token, dict):
            return PredicateResult(
                passed=False,
                expected=f"consent token for '{event.tool_name}'",
                actual="no token",
                message=f"Tool '{event.tool_name}' requires a consent token (none presented)",
            )

        import hmac

        expected = _action_sig(event.tool_name, event.tool_args, bind_args, secret)
        if not hmac.compare_digest(str(token.get("sig", "")), expected):
            return PredicateResult(
                passed=False,
                expected="consent token bound to this action",
                actual="signature mismatch",
                message=f"Consent token does not match this '{event.tool_name}' call (wrong action/args or bad secret)",
            )

        if max_age_s is not None:
            import time

            issued = token.get("issued_at")
            if not isinstance(issued, (int, float)) or (time.time() - issued) > max_age_s:
                return PredicateResult(
                    passed=False,
                    expected=f"token issued within {max_age_s:.0f}s",
                    actual=f"issued_at={issued!r}",
                    message=f"Consent token for '{event.tool_name}' is expired or undated",
                )
        return PredicateResult(passed=True)

    check.predicate_name = "consent_token_required"  # type: ignore[attr-defined]
    return check


@predicate("multi_party_approval_required", owasp=("ASI03", "ASI09",))
def multi_party_approval_required(
    tools,
    n_required: int = 2,
    approvers=None,
    *,
    bind_args: list[str] | None = None,
    token_key: str = "approvals",
    max_age_s: float | None = 600,
    secret=None,
):
    """Dual-control: a high-risk tool needs a quorum of distinct signed approvals.

    A call to a tool in ``tools`` passes only when at least ``n_required`` valid,
    unexpired, action-bound approval tokens from **distinct** approver identities
    are presented at ``event.metadata[token_key]`` (or ``state.metadata`` as a
    fallback) — the classic two-person rule for irreversible actions (wire
    transfers, prod deploys). Two tokens from the same approver count once.

    Each token is ``{"approver", "action", "sig", "issued_at"}`` from
    :func:`mint_approval_token`. The signature covers the approver id and the
    bound argument values, so a token can't be re-pointed to another approver or
    a different call. ``approvers`` (if given) restricts who may sign; ``secret``
    upgrades the signature to an HMAC.
    """
    tools_set = {tools} if isinstance(tools, str) else set(tools)
    approvers_set = set(approvers) if approvers else None

    def check(event: Event, state: SessionState) -> PredicateResult:
        if event.kind != EventKind.TOOL_CALL or event.tool_name not in tools_set:
            return PredicateResult(passed=True)
        raw = (event.metadata or {}).get(token_key)
        if raw is None:
            raw = (state.metadata or {}).get(token_key)
        if isinstance(raw, dict):
            tokens = [raw]
        elif isinstance(raw, (list, tuple)):
            tokens = list(raw)
        else:
            tokens = []

        import hmac
        import time

        approved: set = set()
        for tok in tokens:
            if not isinstance(tok, dict):
                continue
            approver = tok.get("approver")
            if not approver:
                continue
            if approvers_set is not None and approver not in approvers_set:
                continue
            expected = _approval_sig(approver, event.tool_name, event.tool_args, bind_args, secret)
            if not hmac.compare_digest(str(tok.get("sig", "")), expected):
                continue
            if max_age_s is not None:
                issued = tok.get("issued_at")
                if not isinstance(issued, (int, float)) or (time.time() - issued) > max_age_s:
                    continue
            approved.add(approver)

        n = len(approved)
        return PredicateResult(
            passed=n >= n_required,
            expected=f">= {n_required} distinct approvals for '{event.tool_name}'",
            actual=f"{n} valid distinct approval(s)",
            message=f"Tool '{event.tool_name}' needs {n_required} distinct approvals; got {n}",
        )

    check.predicate_name = "multi_party_approval_required"  # type: ignore[attr-defined]
    return check


def mint_consent_token(
    action: str,
    *,
    args: dict | None = None,
    bind_args: list[str] | None = None,
    secret=None,
    issued_at: float | None = None,
) -> dict:
    """Produce a consent token for :func:`consent_token_required` (host-side).

    Sign the exact ``action`` (tool name) and, if ``bind_args`` is given, the
    values of those argument paths in ``args`` — so the token only validates a
    call carrying the same values. ``issued_at`` defaults to ``time.time()``.
    """
    import time

    sig = _action_sig(action, args or {}, bind_args, secret)
    return {
        "action": action,
        "sig": sig,
        "issued_at": time.time() if issued_at is None else issued_at,
    }


def mint_approval_token(
    approver: str,
    *,
    tool: str,
    args: dict | None = None,
    bind_args: list[str] | None = None,
    secret=None,
    issued_at: float | None = None,
) -> dict:
    """Produce one approver's token for :func:`multi_party_approval_required`."""
    import time

    sig = _approval_sig(approver, tool, args or {}, bind_args, secret)
    return {
        "approver": approver,
        "action": tool,
        "sig": sig,
        "issued_at": time.time() if issued_at is None else issued_at,
    }

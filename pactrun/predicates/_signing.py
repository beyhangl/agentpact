"""Internal helpers for signing consent / approval tokens.

Shared by ``consent_token_required`` and ``multi_party_approval_required`` (and
their ``mint_*`` companions). Not part of the public API — import paths here may
change without notice.
"""

from __future__ import annotations

from typing import Any

from pactrun.predicates._argpath import _resolve_path


def _canonical_action(action: str, tool_args, bind_args) -> str:
    """Stable canonical string of (action, bound-arg values) for signing."""
    import json

    payload: dict[str, Any] = {"action": action}
    if bind_args:
        payload["args"] = {k: _resolve_path(tool_args or {}, k)[1] for k in bind_args}
    return json.dumps(payload, sort_keys=True, default=str)


def _action_sig(action: str, tool_args, bind_args, secret) -> str:
    """Signature binding a consent token to an action: HMAC if secret, else sha256."""
    import hashlib
    import hmac

    msg = _canonical_action(action, tool_args, bind_args).encode("utf-8")
    if secret:
        key = secret if isinstance(secret, (bytes, bytearray)) else str(secret).encode("utf-8")
        return hmac.new(key, msg, hashlib.sha256).hexdigest()
    return hashlib.sha256(msg).hexdigest()


def _approval_sig(approver: str, action: str, tool_args, bind_args, secret) -> str:
    """Signature for an approval token, binding the approver id + action + args."""
    import hashlib
    import hmac
    import json

    payload: dict[str, Any] = {"approver": approver, "action": action}
    if bind_args:
        payload["args"] = {k: _resolve_path(tool_args or {}, k)[1] for k in bind_args}
    msg = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    if secret:
        key = secret if isinstance(secret, (bytes, bytearray)) else str(secret).encode("utf-8")
        return hmac.new(key, msg, hashlib.sha256).hexdigest()
    return hashlib.sha256(msg).hexdigest()

"""Recovery — route contract violations to log / warn / block / escalate / retry / fallback."""

from pactrun.recovery.approval import auto_approver, cli_approver
from pactrun.recovery.digest import Digest, digest
from pactrun.recovery.engine import (
    EscalationError,
    FallbackSignal,
    RetrySignal,
    apply_recovery,
)
from pactrun.recovery.webhook import webhook_handler

__all__ = [
    "apply_recovery",
    "EscalationError",
    "RetrySignal",
    "FallbackSignal",
    "webhook_handler",
    "cli_approver",
    "auto_approver",
    "digest",
    "Digest",
]

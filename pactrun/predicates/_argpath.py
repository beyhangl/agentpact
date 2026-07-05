"""Internal helpers for reading and matching tool-argument values.

Shared by the tool-argument, rate-limit, and signing predicates. Not part of
the public API — import paths here may change without notice.
"""

from __future__ import annotations


def _args_blob(tool_args) -> str:
    import json

    if not tool_args:
        return ""
    try:
        return json.dumps(tool_args, default=str)
    except (TypeError, ValueError):
        return str(tool_args)


def _looks_like_path(value: str) -> bool:
    return ("/" in value) or ("\\" in value) or value.startswith("~")


def _resolve_path(obj, path: str):
    """Walk a dotted path (dict keys + int list indices). Returns (found, value).

    ``"recipient.email"`` descends dict keys; numeric segments index lists or
    tuples (negative indices allowed). Returns ``(False, None)`` if any segment
    is absent or the container type doesn't match.
    """
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return False, None
            cur = cur[part]
        elif isinstance(cur, (list, tuple)):
            try:
                idx = int(part)
            except ValueError:
                return False, None
            if -len(cur) <= idx < len(cur):
                cur = cur[idx]
            else:
                return False, None
        else:
            return False, None
    return True, cur


def _value_in(value: str, entries: set, match: str) -> bool:
    """True if ``value`` matches any of ``entries`` under the given match mode."""
    if match == "exact":
        return value in entries
    if match == "ci":
        v = value.casefold()
        return any(v == e.casefold() for e in entries)
    if match == "glob":
        from fnmatch import fnmatch

        return any(fnmatch(value, e) for e in entries)
    if match == "regex":
        import re

        return any(re.search(e, value) for e in entries)
    return False

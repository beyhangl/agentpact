"""Internal helpers for host/URL extraction and matching (egress guards).

Shared by ``tool_host_within`` and ``no_exfil_links``. Not part of the public
API — import paths here may change without notice.
"""

from __future__ import annotations


def _as_ip(host: str):
    import ipaddress

    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _extract_host(value: str):
    """Pull the host out of a URL or bare host[:port][/path]; lowercased, no brackets."""
    from urllib.parse import urlsplit

    v = value.strip()
    if not v:
        return None
    try:
        netloc_form = v if ("://" in v or v.startswith("//")) else "//" + v
        host = urlsplit(netloc_form).hostname
    except ValueError:
        return None
    return host.lower() if host else None


def _url_like(value: str) -> bool:
    """Heuristic: is this string worth treating as a URL/host for egress checks?"""
    v = value.strip()
    if not v or any(ch.isspace() for ch in v):
        return False
    if "://" in v:
        return True
    head = v.split("/")[0]
    hostpart = head.rsplit(":", 1)[0].strip("[]")
    if hostpart == "localhost":
        return True
    if _as_ip(hostpart) is not None:
        return True
    return ("." in hostpart) and all(ch.isalnum() or ch in ".-" for ch in hostpart)


def _host_matches(host: str, patterns: list[str]) -> bool:
    """True if host matches any glob host pattern or IP/CIDR in ``patterns``."""
    import ipaddress
    from fnmatch import fnmatch

    host_ip = _as_ip(host)
    for p in patterns:
        pl = p.lower()
        if host_ip is not None:
            try:
                net = ipaddress.ip_network(p, strict=False)
            except ValueError:
                net = None
            if net is not None and host_ip.version == net.version and host_ip in net:
                return True
        if fnmatch(host, pl):
            return True
    return False


def _is_private_host(host: str) -> bool:
    """True for localhost or a private/loopback/link-local/reserved IP literal."""
    if host == "localhost":
        return True
    ip = _as_ip(host)
    if ip is None:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved

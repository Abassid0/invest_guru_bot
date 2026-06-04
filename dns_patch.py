"""
DNS fallback patch.
When the system DNS (router) fails to resolve a hostname, this falls back
to querying 8.8.8.8 (Google DNS) directly — always preferring IPv4 (A records).
Import this module BEFORE any database/network calls.
"""
import socket
import dns.resolver

_original_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _original_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        pass

    # System DNS failed — query 8.8.8.8 directly, prefer IPv4
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = ["8.8.8.8", "8.8.4.4"]
    resolver.timeout = 5
    resolver.lifetime = 10

    for record_type in ("A", "AAAA"):
        try:
            answers = resolver.resolve(host, record_type)
            ip = str(answers[0])
            af = socket.AF_INET if record_type == "A" else socket.AF_INET6
            return _original_getaddrinfo(ip, port, af, type, proto, flags)
        except Exception:
            continue

    raise socket.gaierror(f"dns_patch: could not resolve {host} via 8.8.8.8")


def apply():
    if socket.getaddrinfo is not _patched_getaddrinfo:
        socket.getaddrinfo = _patched_getaddrinfo


import sys as _sys, os as _os
# Only patch on Windows — Linux servers (Railway, etc.) have working system DNS
if _sys.platform == "win32" and not _os.getenv("RAILWAY_SERVICE_ID"):
    apply()

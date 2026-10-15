"""Typed provider indicators. These functions never resolve or contact an indicator."""

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit


def public_ip(value):
    address = ipaddress.ip_address(value)
    if not address.is_global:
        raise ValueError("A public IP address is required")
    return str(address)


def domain(value):
    value = value.rstrip(".").encode("idna").decode("ascii").lower()
    if len(value) > 253 or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", value):
        raise ValueError("Invalid indicator domain")
    return value


def observed_indicator(kind, value):
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise ValueError("Invalid indicator value")
    value = value.strip()
    port = None
    if kind == "ip:port":
        host, separator, number = value.rpartition(":")
        if not separator or not number.isdecimal() or not 1 <= int(number) <= 65535:
            raise ValueError("Invalid indicator port")
        value, port, kind = public_ip(host.strip("[]")), int(number), "ip"
    elif kind == "ip":
        value = public_ip(value)
    elif kind == "domain":
        value = domain(value)
    elif kind == "url":
        parsed = urlsplit(value)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Invalid indicator URL")
        try:
            host = public_ip(parsed.hostname)
            if ":" in host:
                host = "[" + host + "]"
        except ValueError:
            # Numeric addresses must pass public-IP validation, not the domain path.
            try:
                ipaddress.ip_address(parsed.hostname)
            except ValueError:
                host = domain(parsed.hostname)
            else:
                raise ValueError("Indicator URL requires a public host") from None
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("Invalid indicator URL port")
        authority = host + (f":{parsed.port}" if parsed.port is not None else "")
        value = urlunsplit((parsed.scheme.lower(), authority, parsed.path or "/", parsed.query, ""))
    elif kind in {"hash", "md5_hash", "sha1_hash", "sha256_hash"}:
        lengths = {"md5_hash": [32], "sha1_hash": [40], "sha256_hash": [64], "hash": [32, 40, 64]}
        if len(value) not in lengths[kind] or not re.fullmatch(r"[a-fA-F0-9]+", value):
            raise ValueError("Invalid indicator hash")
        kind, value = "hash", value.lower()
    else:
        raise ValueError("Unsupported provider indicator type")
    return kind, value, port

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_EXACT = {
    "gclid", "fbclid", "msclkid", "yclid", "igshid", "_openstat", "utm_source",
}
_TRACKING_PREFIXES = ("utm_", "pk_", "mc_", "pi_", "sk_", "cmpid", "cpi_")


def _is_tracking_param(key: str) -> bool:
    k = key.lower()
    return (
        k in _TRACKING_EXACT
        or k.startswith(_TRACKING_PREFIXES)
        or k.endswith("clid")  
    )


def normalize_url(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    host = parts.netloc.lower()
    if not host or "." not in host.split(":")[0]:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    query = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(k)
    )
    return urlunsplit(("https", host, parts.path or "/", urlencode(query), ""))


def domain_bucket(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    host = host.split(":")[0].split("@")[-1]
    if host.startswith("www."):
        host = host[4:]
    return host

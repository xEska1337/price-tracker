from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from soupsieve import SelectorSyntaxError

from app.config import get_settings
from app.scraping.adapters import Adapter, load_adapters

ALLOWED_SELECTOR_KEYS = ("price", "title", "image")
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9-]+$")
MAX_SELECTOR_LEN = 300


class AdapterValidationError(ValueError):
    pass


def user_adapters_dir() -> Path:
    directory = Path(get_settings().adapters_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def normalize_domain(value: str) -> str:
    domain = (value or "").strip().lower()
    domain = domain.removeprefix("https://").removeprefix("http://")
    domain = domain.split("/")[0].split(":")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    if domain != "localhost" and not _IPV4_RE.match(domain) and not _DOMAIN_RE.match(domain):
        raise AdapterValidationError(f"'{value}' is not a valid domain")
    return domain


def parse_adapter_json(raw: str) -> dict:
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise AdapterValidationError("The pasted text does not contain a JSON object")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AdapterValidationError(f"Invalid JSON: {exc.msg} (line {exc.lineno})") from exc


def validate_adapter(spec: dict, expected_domain: str | None = None) -> tuple[str, dict]:
    if not isinstance(spec, dict):
        raise AdapterValidationError("Adapter must be a JSON object")
    raw_domain = spec.get("domain") or expected_domain
    if not raw_domain:
        raise AdapterValidationError("Adapter is missing the 'domain' field")
    domain = normalize_domain(str(raw_domain))
    if expected_domain:
        expected = normalize_domain(expected_domain)
        if domain != expected and not domain.endswith("." + expected) and not expected.endswith("." + domain):
            raise AdapterValidationError(
                f"Adapter domain '{domain}' does not match the product's store '{expected}'"
            )

    selectors = spec.get("selectors")
    if not isinstance(selectors, dict) or not selectors:
        raise AdapterValidationError("Adapter must contain a non-empty 'selectors' object")

    clean: dict[str, str] = {}
    for key in ALLOWED_SELECTOR_KEYS:
        value = selectors.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise AdapterValidationError(f"Selector '{key}' must be a non-empty string")
        value = value.strip()
        if len(value) > MAX_SELECTOR_LEN:
            raise AdapterValidationError(f"Selector '{key}' is too long")
        if "javascript:" in value.lower():
            raise AdapterValidationError(f"Selector '{key}' is not a CSS selector")
        try:
            BeautifulSoup("", "lxml").select_one(value)
        except SelectorSyntaxError as exc:
            raise AdapterValidationError(f"Selector '{key}' is not valid CSS: {exc}") from exc
        clean[key] = value

    if "price" not in clean:
        raise AdapterValidationError("Adapter must define a 'price' selector")

    currency = spec.get("currency")
    if currency is not None:
        currency = str(currency).strip().upper()[:8] or None

    return domain, {"domain": domain, "selectors": clean, "currency": currency}


def save_user_adapter(domain: str, spec: dict) -> Path:
    path = user_adapters_dir() / f"{domain}.json"
    path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def delete_user_adapter(domain: str) -> bool:
    path = user_adapters_dir() / f"{normalize_domain(domain)}.json"
    if path.is_file():
        path.unlink()
        return True
    return False


def list_user_adapters() -> list[dict]:
    adapters: list[dict] = []
    for path in sorted(user_adapters_dir().glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        adapters.append(
            {
                "domain": raw.get("domain", path.stem),
                "selectors": raw.get("selectors", {}),
                "currency": raw.get("currency"),
                "file": path.name,
            }
        )
    return adapters


def load_all_adapters() -> list[Adapter]:
    from app.scraping.adapters import ADAPTERS_DIR

    return load_adapters(user_adapters_dir()) + load_adapters(ADAPTERS_DIR)

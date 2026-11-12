from __future__ import annotations

import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

MAX_HTML_CHARS = 12_000
MAX_CANDIDATES = 8
MAX_PROMPT_CHARS = 18_000

_PRICE_RE = re.compile(
    r"(?:\d{1,3}(?:[ \u00a0.,]\d{3})+|\d+)(?:[.,]\d{1,2})?\s*(?:zł|PLN|EUR|€|\$|£|GBP|USD)",
    re.IGNORECASE,
)
_NUMBER_PRICE_RE = re.compile(r"\b\d+[.,]\d{2}\b")

_NOISE_TAGS = ("script", "style", "noscript", "svg", "template", "iframe", "link")


def clean_html(html: str, max_chars: int = MAX_HTML_CHARS) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, type(soup.Comment))):
        comment.extract()
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.startswith("on") or attr.startswith("data-") and len(str(tag.attrs[attr])) > 120:
                del tag.attrs[attr]
    body = soup.body or soup
    text = str(body)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text[:max_chars]


def _css_path(element) -> str:
    parts: list[str] = []
    node = element
    for _ in range(4):
        if node is None or node.name in ("[document]", "html"):
            break
        label = node.name
        if node.get("id"):
            label += f"#{node['id']}"
        elif node.get("class"):
            label += "." + ".".join(str(c) for c in node["class"][:2])
        parts.append(label)
        node = node.parent
    return " > ".join(reversed(parts))


def find_price_candidates(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    seen: set[int] = set()
    candidates: list[str] = []
    for text_node in soup.find_all(string=_PRICE_RE):
        parent = text_node.parent
        if parent is None or id(parent) in seen:
            continue
        seen.add(id(parent))
        snippet = re.sub(r"\s+", " ", parent.get_text(" ", strip=True))[:90]
        if not snippet:
            continue
        rendered = str(parent)[:400]
        candidates.append(f"<{_css_path(parent)}>  text: {snippet}\n    markup: {rendered}")
        if len(candidates) >= MAX_CANDIDATES:
            break
    if not candidates:
        for text_node in soup.find_all(string=_NUMBER_PRICE_RE):
            parent = text_node.parent
            if parent is None or id(parent) in seen:
                continue
            seen.add(id(parent))
            snippet = re.sub(r"\s+", " ", parent.get_text(" ", strip=True))[:90]
            candidates.append(f"<{_css_path(parent)}>  text: {snippet}\n    markup: {str(parent)[:400]}")
            if len(candidates) >= MAX_CANDIDATES:
                break
    return candidates


def build_adapter_prompt(url: str, html: str, domain: str | None = None) -> str:
    domain = domain or (urlsplit(url).hostname or "")
    candidates = find_price_candidates(html)
    candidate_block = "\n\n".join(f"{i + 1}. {c}" for i, c in enumerate(candidates)) or (
        "(no obvious price elements found — infer the selector from the HTML below)"
    )
    cleaned = clean_html(html)

    prompt = f"""You are helping me add support for an online store to "PriceTrack", a self-hosted price tracker.

I will give you (a) the URL/domain and (b) a cleaned-up snapshot of the product page HTML.
Produce a JSON "adapter" with CSS selectors that let PriceTrack read the price, title and image.

Reply with ONE fenced ```json block and nothing else.

Required shape:
```json
{{
  "domain": "{domain}",
  "currency": "PLN",
  "selectors": {{
    "price": "CSS selector of the element whose text contains the price",
    "title": "CSS selector of the product name",
    "image": "CSS selector of the main product image"
  }}
}}
```

Rules:
- Use only standard CSS selectors that exist in the HTML below. No XPath, no :contains(), no invented classes.
- The price selector must match exactly one element and that element's own text must contain the price (e.g. "1 299,00 zł"), not a container that also holds other prices.
- The image selector should point at an <img> (PriceTrack reads src/data-src) or at <meta property="og:image">.
- The title selector can be omitted if there is no clear one.
- currency must be an ISO code (PLN, EUR, USD, GBP) inferred from the page.

Page URL: {url}
Domain: {domain}

Likely price elements (tag path, visible text, markup):
{candidate_block}

Cleaned HTML (scripts/styles removed, truncated to {MAX_HTML_CHARS} characters):
```html
{cleaned}
```
"""
    return prompt[:MAX_PROMPT_CHARS]

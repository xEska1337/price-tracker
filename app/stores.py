from __future__ import annotations

TIER_LABELS = {
    "jsonld": "JSON-LD",
    "opengraph": "OpenGraph",
    "adapter": "site adapter",
    "browser": "browser fallback",
}

SUPPORTED_STORES: list[dict] = [
    {
        "domain": "x-kom.pl",
        "name": "x-kom",
        "tier": "jsonld",
        "verified": True,
        "note": "Product pages expose schema.org data; images and prices parse cleanly.",
    },
    {
        "domain": "ikea.com",
        "name": "IKEA",
        "tier": "jsonld",
        "verified": True,
        "note": "Works with the Polish storefront (ikea.com/pl/pl).",
    },
    {
        "domain": "komputronik.pl",
        "name": "Komputronik",
        "tier": "jsonld",
        "verified": True,
        "note": "JSON-LD + OpenGraph on product pages.",
    },
    {
        "domain": "neonet.pl",
        "name": "Neonet",
        "tier": "jsonld",
        "verified": True,
        "note": "JSON-LD + OpenGraph on product pages.",
    },
    {
        "domain": "mediaexpert.pl",
        "name": "Media Expert",
        "tier": "browser",
        "verified": True,
        "note": "Blocked over plain HTTP (403); needs the headless-browser fallback (on by default).",
    },
    {
        "domain": "rossmann.pl",
        "name": "Rossmann",
        "tier": "jsonld",
        "verified": True,
        "note": "Beauty/drugstore product pages carry schema.org data.",
    },
    {
        "domain": "sportano.pl",
        "name": "Sportano",
        "tier": "jsonld",
        "verified": True,
        "note": "Sports equipment; JSON-LD + OpenGraph on product pages.",
    },
    {
        "domain": "sferis.pl",
        "name": "Sferis",
        "tier": "jsonld",
        "verified": True,
        "note": "Electronics; product pages expose JSON-LD + OpenGraph.",
    },
]

KNOWN_BLOCKED: list[dict] = [
    {
        "domain": "allegro.pl",
        "name": "Allegro",
        "note": "Strong bot protection; usually fails even through the browser.",
    },
    {
        "domain": "amazon.pl",
        "name": "Amazon",
        "note": "Frequently serves a captcha to automated clients.",
    },
    {
        "domain": "euro.com.pl",
        "name": "Euro RTV AGD",
        "note": "Blocks plain HTTP requests; try the browser fallback.",
    },
]


def stores_payload() -> dict:
    return {
        "tiers": TIER_LABELS,
        "stores": SUPPORTED_STORES,
        "blocked": KNOWN_BLOCKED,
    }

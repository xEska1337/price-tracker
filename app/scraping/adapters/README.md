# Per-domain adapters

Fallback tier (tier 3) for stores that expose no JSON-LD / OpenGraph price.
JSON-LD (tier 1) and OpenGraph (tier 2) cover most shops; only add an adapter
when logs show `price not found` for that domain.

One JSON file per domain:

```json
{
  "domain": "example.com",
  "currency": "PLN",
  "selectors": {
    "price": "product-price-selector (text is parsed as price)",
    "title": "h1-selector",
    "image": "img-selector (src / data-src used)"
  }
}
```

Matching: file is used when the product host equals `domain` or ends with `.domain`.

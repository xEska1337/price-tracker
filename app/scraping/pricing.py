from __future__ import annotations

import re
import unicodedata

_WS = "\u00a0\u2007\u2009\u202f\u2028\u2029\u200b\ufeff "
_MAX_SANE_PRICE = 10_000_000


def parse_price_number(text: str | int | float | None) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        value = float(text)
    else:
        s = unicodedata.normalize("NFC", text)
        s = s.translate({ord(c): None for c in _WS})
        s = re.sub(r"[^\d,.\-]", "", s)  
        s = re.sub(r"(?<!^)-|-(?!\d)", "", s)  
        if not s or s in {"-", ".", ","}:
            return None
        last_comma, last_dot = s.rfind(","), s.rfind(".")
        if last_comma != -1 and last_dot != -1:
            if last_comma > last_dot:
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        else:
            sep = "," if last_comma != -1 else "." if last_dot != -1 else None
            if sep is not None:
                count = s.count(sep)
                digits_after = len(s) - s.rfind(sep) - 1
                trailing_group = s[s.rfind(sep) + 1 :]
                if count > 1 or (digits_after == 3 and trailing_group.isdigit()):
                    s = s.replace(sep, "")
                else:
                    s = s.replace(sep, ".")
        try:
            value = float(s)
        except ValueError:
            return None
    if value <= 0 or value > _MAX_SANE_PRICE:
        return None
    return round(value, 2)


_CURRENCY_HINTS = (
    ("PLN", "PLN"), ("zł", "PLN"), ("zloty", "PLN"),
    ("€", "EUR"), ("EUR", "EUR"),
    ("$", "USD"), ("USD", "USD"),
    ("£", "GBP"), ("GBP", "GBP"),
)


def guess_currency(text: str | None, default: str | None = None) -> str | None:
    if not text:
        return default
    for token, code in _CURRENCY_HINTS:
        if token in text:
            return code
    return default

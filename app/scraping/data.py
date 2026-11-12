from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedData:
    title: str | None = None
    image: str | None = None
    price: float | None = None
    currency: str | None = None
    in_stock: bool = True
    extractor: str | None = None

    def has_price(self) -> bool:
        return self.price is not None

    def is_empty(self) -> bool:
        return not any((self.title, self.image, self.has_price()))

    def merge_from(self, other: "ExtractedData | None") -> "ExtractedData":
        if other is None:
            return self
        if self.title is None and other.title:
            self.title = other.title
        if self.image is None and other.image:
            self.image = other.image
        if self.price is None and other.price is not None:
            self.price = other.price
            self.currency = self.currency or other.currency
            self.in_stock = other.in_stock
        if self.currency is None:
            self.currency = other.currency
        if self.extractor and other.extractor and other.extractor not in self.extractor:
            self.extractor = f"{self.extractor}+{other.extractor}"
        elif self.extractor is None:
            self.extractor = other.extractor
        return self


@dataclass
class ScrapeResult:
    ok: bool
    http_status: int | None = None
    extractor: str | None = None
    error: str | None = None
    data: ExtractedData = field(default_factory=ExtractedData)
    final_url: str | None = None
    notified: bool = False
    failure_kind: str | None = None

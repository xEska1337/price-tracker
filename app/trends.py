from __future__ import annotations

from datetime import datetime, timedelta

Point = tuple[datetime, float]

_SPARK_MAX_POINTS = 40
_SPARK_DAYS = 30


def pct_change(base: float | None, value: float | None) -> float | None:
    if base in (None, 0.0) or value is None:
        return None
    return round((value - base) / base * 100.0, 2)


def _baseline(points: list[Point], window_days: int, now: datetime) -> float | None:
    cutoff = now - timedelta(days=window_days)
    base: float | None = None
    for at, price in points:  
        if at <= cutoff:
            base = price
        else:
            break
    return base


def compute_deltas(points: list[Point], now: datetime) -> dict[str, float | None]:
    current = points[-1][1] if points else None
    return {
        "delta_1d_pct": pct_change(_baseline(points, 1, now), current),
        "delta_7d_pct": pct_change(_baseline(points, 7, now), current),
        "delta_30d_pct": pct_change(_baseline(points, 30, now), current),
    }


def compute_stats(points: list[Point], now: datetime) -> dict:
    if not points:
        return {
            "min": None, "max": None, "avg": None, "current": None,
            "at_all_time_low": False,
            "delta_1d_pct": None, "delta_7d_pct": None, "delta_30d_pct": None,
        }
    values = [price for _, price in points]
    current = values[-1]
    lowest = min(values)
    return {
        "min": round(lowest, 2),
        "max": round(max(values), 2),
        "avg": round(sum(values) / len(values), 2),
        "current": round(current, 2),
        "at_all_time_low": len(values) >= 2 and current <= lowest + 1e-9,
        **compute_deltas(points, now),
    }


def moving_average(points: list[Point], days: int = 7) -> list[Point]:
    if len(points) < 3:
        return []
    window = timedelta(days=days)
    out: list[Point] = []
    start = 0
    for i, (at, _) in enumerate(points):
        while points[start][0] < at - window:
            start += 1
        chunk = [price for _, price in points[start : i + 1]]
        out.append((at, round(sum(chunk) / len(chunk), 2)))
    return out


def sparkline_values(points: list[Point], now: datetime,
                     max_points: int = _SPARK_MAX_POINTS, days: int = _SPARK_DAYS) -> list[float]:
    recent = [(p, at) for at, p in points if at >= now - timedelta(days=days)]
    if not recent:
        recent = [(p, at) for at, p in points][-max_points:]
    values = [price for price, _ in recent]
    if len(values) <= max_points:
        return values
    step = (len(values) - 1) / (max_points - 1)
    return [values[round(i * step)] for i in range(max_points)]


def filter_range(points: list[Point], days: int | None, now: datetime) -> list[Point]:
    if days is None:
        return points
    cutoff = now - timedelta(days=days)
    return [p for p in points if p[0] >= cutoff]

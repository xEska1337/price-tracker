from datetime import datetime, timedelta, timezone

from app.trends import (
    compute_deltas,
    compute_stats,
    filter_range,
    moving_average,
    pct_change,
    sparkline_values,
)

NOW = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)


def points(*days_back_price) -> list[tuple[datetime, float]]:
    return sorted(
        [(NOW - timedelta(days=d), p) for d, p in days_back_price]
    )


def test_pct_change():
    assert pct_change(100, 90) == -10.0
    assert pct_change(0, 5) is None
    assert pct_change(None, 5) is None


def test_deltas_use_price_at_or_before_window():
    pts = points((0, 80.0), (2, 90.0), (8, 100.0), (35, 120.0))
    deltas = compute_deltas(pts, NOW)
    assert deltas["delta_1d_pct"] == -11.11
    assert deltas["delta_7d_pct"] == -20.0
    assert deltas["delta_30d_pct"] == round((80 - 120) / 120 * 100, 2)


def test_deltas_none_when_no_history_beyond_window():
    pts = points((0, 50.0), (1, 55.0))
    deltas = compute_deltas(pts, NOW)
    assert deltas["delta_30d_pct"] is None


def test_stats_and_all_time_low():
    pts = points((10, 100.0), (5, 90.0), (1, 95.0))
    stats = compute_stats(pts, NOW)
    assert stats["min"] == 90.0
    assert stats["max"] == 100.0
    assert stats["current"] == 95.0
    assert stats["at_all_time_low"] is False
    pts_low = points((10, 100.0), (5, 90.0))
    assert compute_stats(pts_low, NOW)["at_all_time_low"] is True


def test_moving_average_short_series_empty():
    assert moving_average(points((0, 10.0), (1, 12.0))) == []
    series = moving_average(points((0, 10.0), (1, 12.0), (2, 14.0)))
    assert len(series) == 3
    assert series[-1][1] == 12.0  


def test_sparkline_strides_large_series():
    pts = [(NOW - timedelta(hours=i), 100.0 + i) for i in range(500)]
    pts.reverse()
    spark = sparkline_values(pts, NOW, max_points=40)
    assert len(spark) == 40
    assert spark[0] == 599.0  
    assert spark[-1] == 100.0  


def test_filter_range():
    pts = points((0, 1.0), (10, 2.0), (40, 3.0))
    assert len(filter_range(pts, 30, NOW)) == 2
    assert len(filter_range(pts, None, NOW)) == 3

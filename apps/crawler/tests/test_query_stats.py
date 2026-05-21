from web_search_crawler.db.url_queries import (
    _estimate_tail_ratio_from_histogram,
    _parse_histogram_bounds,
)


def test_parse_histogram_bounds_from_pg_stats_string():
    assert _parse_histogram_bounds("{1,2,3.5}") == [1.0, 2.0, 3.5]


def test_estimate_tail_ratio_from_histogram_handles_midpoint_cutoff():
    ratio = _estimate_tail_ratio_from_histogram([0.0, 10.0, 20.0], 15)

    assert ratio is not None
    assert ratio == 0.25


def test_estimate_tail_ratio_from_histogram_handles_full_and_empty_ranges():
    assert _estimate_tail_ratio_from_histogram([0.0, 10.0], -1) == 1.0
    assert _estimate_tail_ratio_from_histogram([0.0, 10.0], 10) == 0.0

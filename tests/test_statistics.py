"""The cumulative-sum math behind the Energy-dashboard backfill.

Only the pure boundary-point builder is exercised here; the actual write to
Home Assistant's recorder needs a running HA and is validated in the live
runtime, not in this suite.
"""

from datetime import date
from itertools import pairwise

from custom_components.epcube.statistics import _cumulative_points


def test_cumulative_points_reconstruct_each_days_energy():
    daily = [
        (date(2026, 9, 1), 2.0),
        (date(2026, 9, 2), 3.0),
        (date(2026, 9, 3), 1.5),
    ]
    points = _cumulative_points(daily)

    # A point per day carrying the sum *before* that day, plus a trailing
    # boundary one day past the last so the final day still has a delta.
    assert points == [
        (date(2026, 9, 1), 0.0),
        (date(2026, 9, 2), 2.0),
        (date(2026, 9, 3), 5.0),
        (date(2026, 9, 4), 6.5),
    ]

    # The Energy dashboard reads day D as sum(D+1) - sum(D); that must give the
    # day's own energy back.
    sums = [total for _day, total in points]
    deltas = [round(b - a, 3) for a, b in pairwise(sums)]
    assert deltas == [2.0, 3.0, 1.5]


def test_cumulative_points_empty():
    assert _cumulative_points([]) == []

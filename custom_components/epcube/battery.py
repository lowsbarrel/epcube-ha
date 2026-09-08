"""Derived battery-energy counters.

The API reports battery power (W) and stored energy (kWh) but leaves its own
battery *energy* counters at zero, so charged/discharged kWh are derived here by
differencing the stored-energy reading between refreshes: a rise is energy in, a
fall is energy out.

A small threshold with a held anchor keeps the reading's 0.01 kWh quantisation
from accruing as phantom throughput - a genuine slow flow still crosses it after
a few refreshes, measured against the anchor rather than the last sample. Only
net movement within a refresh interval is seen, so a charge that fully reverses
between two reads is missed; this is a best-effort figure, most accurate when
refreshes are frequent.
"""

from __future__ import annotations


class BatteryEnergyAccumulator:
    """Running charged and discharged energy since the process started, kWh."""

    # Below this the stored reading is dominated by its own quantisation, so the
    # anchor is held rather than moved - real change still accrues against it.
    MIN_DELTA_KWH = 0.05

    def __init__(self) -> None:
        self.charged = 0.0
        self.discharged = 0.0
        self._anchor: float | None = None

    def update(self, stored: float | None) -> None:
        """Fold one stored-energy reading (kWh) into the totals."""
        if stored is None:
            return
        if self._anchor is None:
            self._anchor = stored
            return
        delta = stored - self._anchor
        if delta >= self.MIN_DELTA_KWH:
            self.charged += delta
            self._anchor = stored
        elif delta <= -self.MIN_DELTA_KWH:
            self.discharged += -delta
            self._anchor = stored

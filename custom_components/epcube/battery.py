from __future__ import annotations


class BatteryEnergyAccumulator:
    # Quantisation is 0.01 kWh; hold the anchor below this so slow flow still accrues.
    MIN_DELTA_KWH = 0.05

    def __init__(self) -> None:
        self.charged = 0.0
        self.discharged = 0.0
        self._anchor: float | None = None

    def update(self, stored: float | None) -> None:
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

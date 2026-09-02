"""One call's worth of everything - what a polling consumer wants per cycle."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field

from .base import EpCubeModel
from .device import DeviceDetail, DeviceSummary, NetworkInfo, OutageEvent, PvStrings
from .energy import EnergySeries, EnergyTotals
from .live import LiveSnapshot
from .mode import ModeConfig


class Snapshot(EpCubeModel):
    """Live state plus the supporting reads, gathered concurrently.

    Only `live` is required. Every other section is best-effort: a slow or broken
    supplementary endpoint records its error in `errors` and leaves its section
    empty rather than failing the whole cycle. That matters because the
    statistics routes are markedly slower than the live one, and on some clusters
    they intermittently time out.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    dev_id: str
    fetched_at: datetime = Field(default_factory=datetime.now)

    live: LiveSnapshot
    mode: ModeConfig | None = None
    detail: DeviceDetail | None = None
    summary: DeviceSummary | None = None
    pv: PvStrings | None = None
    network: NetworkInfo | None = None
    outages: list[OutageEvent] = Field(default_factory=list)

    today: EnergyTotals | None = None
    month: EnergyTotals | None = None
    year: EnergyTotals | None = None
    lifetime: EnergyTotals | None = None
    series: EnergySeries | None = None

    errors: dict[str, str] = Field(default_factory=dict)
    """Section name -> why it is missing. Empty means everything succeeded."""

    @property
    def complete(self) -> bool:
        return not self.errors

    @property
    def battery_power_w(self) -> float | None:
        """Battery power in watts, from the best source available.

        Prefers the series, which reports it directly; falls back to the live
        snapshot's derived value, which carries sampling noise.
        """
        if self.series is not None:
            latest = self.series.latest()
            if latest is not None and latest.node_vo.battery_power_w is not None:
                return latest.node_vo.battery_power_w
        return self.live.battery_power

    @property
    def battery_soc(self) -> int | None:
        return self.live.battery_soc

    def summary_line(self) -> str:
        """A one-line human summary, for logs and CLI output."""
        mode = self.live.mode
        parts = [
            f"SoC {self.battery_soc}%" if self.battery_soc is not None else "SoC ?",
            f"solar {self.live.solar_power:.0f}W" if self.live.solar_power is not None else "",
            f"grid {self.live.grid_power:.0f}W" if self.live.grid_power is not None else "",
            f"load {self.live.load_power:.0f}W" if self.live.load_power is not None else "",
        ]
        battery = self.battery_power_w
        if battery is not None:
            parts.append(f"battery {battery:+.0f}W")
        if mode is not None:
            parts.append(mode.label)
        return "  ".join(p for p in parts if p)

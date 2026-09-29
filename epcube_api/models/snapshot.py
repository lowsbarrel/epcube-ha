from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field

from .base import EpCubeModel
from .device import DeviceDetail, DeviceSummary, NetworkInfo, OutageEvent, PvStrings
from .energy import EnergySeries, EnergyTotals
from .live import LiveSnapshot
from .mode import ModeConfig


class Snapshot(EpCubeModel):
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

    @property
    def complete(self) -> bool:
        return not self.errors

    @property
    def battery_power_w(self) -> float | None:
        if self.series is not None:
            latest = self.series.latest()
            if latest is not None and latest.node_vo.battery_power_w is not None:
                return latest.node_vo.battery_power_w
        return self.live.battery_power

    @property
    def battery_soc(self) -> int | None:
        return self.live.battery_soc

    @property
    def solar_power_w(self) -> float | None:
        if self.series is not None:
            latest = self.series.latest()
            if latest is not None and latest.node_vo.solar_power_w is not None:
                return latest.node_vo.solar_power_w
        if self.pv is not None and self.pv.active:
            return self.pv.total_power_w
        return self.live.solar_power

    @property
    def solar_power_source(self) -> str:
        if self.series is not None and self.series.latest() is not None:
            return "series"
        if self.pv is not None and self.pv.active:
            return "pv_strings"
        return "live"

    def summary_line(self) -> str:
        mode = self.live.mode
        parts = [
            f"SoC {self.battery_soc}%" if self.battery_soc is not None else "SoC ?",
            f"solar {self.solar_power_w:.0f}W" if self.solar_power_w is not None else "",
            f"grid {self.live.grid_power:.0f}W" if self.live.grid_power is not None else "",
            f"load {self.live.load_power:.0f}W" if self.live.load_power is not None else "",
        ]
        battery = self.battery_power_w
        if battery is not None:
            parts.append(f"battery {battery:+.0f}W")
        if mode is not None:
            parts.append(mode.label)
        return "  ".join(p for p in parts if p)

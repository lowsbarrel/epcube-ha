"""Pydantic models for every EP Cube request and response this client speaks."""

from .account import Account, LoginResult
from .base import EpCubeModel, EpCubeRequest
from .device import (
    DeviceDetail,
    DeviceSummary,
    NetworkInfo,
    OutageEvent,
    PvString,
    PvStrings,
    Warranty,
)
from .energy import EnergySeries, EnergyTotals, SeriesPoint, SeriesReading
from .live import LiveSnapshot
from .mode import ModeConfig, ReserveLevels, TouWindow
from .requests import SwitchModeRequest

__all__ = [
    "Account",
    "DeviceDetail",
    "DeviceSummary",
    "EnergySeries",
    "EnergyTotals",
    "EpCubeModel",
    "EpCubeRequest",
    "LiveSnapshot",
    "LoginResult",
    "ModeConfig",
    "NetworkInfo",
    "OutageEvent",
    "PvString",
    "PvStrings",
    "ReserveLevels",
    "SeriesPoint",
    "SeriesReading",
    "SwitchModeRequest",
    "TouWindow",
    "Warranty",
]

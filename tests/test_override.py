from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

import httpx
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.epcube import override as override_mod
from custom_components.epcube.coordinator import EpCubeCoordinator
from custom_components.epcube.override import HOLD, Override, OverrideManager

from .conftest import MODE, Recorder


class FakeStore:
    def __init__(self) -> None:
        self.data: dict[str, Any] | None = None

    async def async_load(self) -> dict[str, Any] | None:
        return self.data

    async def async_save(self, data: dict[str, Any]) -> None:
        self.data = data

    async def async_remove(self) -> None:
        self.data = None


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> FakeStore:
    store = FakeStore()

    def make_store(*args: object, **kwargs: object) -> FakeStore:
        return store

    monkeypatch.setattr(override_mod, "Store", make_store)
    return store


@pytest.fixture
def armed(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    armed: list[datetime] = []

    def track(hass: object, action: object, when: datetime) -> Callable[[], None]:
        armed.append(when)
        return lambda: None

    monkeypatch.setattr(override_mod, "async_track_point_in_utc_time", track)
    return armed


@pytest.fixture
async def manager(
    coordinator: EpCubeCoordinator, store: FakeStore, armed: list[datetime]
) -> OverrideManager:
    manager = OverrideManager(cast(HomeAssistant, None), coordinator, "entry")
    manager.active = Override(kind=HOLD, target_soc=86, ends_at=None, previous_reserve="20")
    await store.async_save(manager.active.as_dict())
    return manager


def test_a_store_from_before_the_fix_still_yields_the_previous_reserve():
    override = Override.from_dict(
        {"kind": HOLD, "target_soc": 40, "baseline": {"selfConsumptioinReserveSoc": "15"}}
    )
    assert override is not None
    assert override.previous_reserve == "15"


async def test_a_failed_restore_keeps_the_override_and_retries(
    manager: OverrideManager, store: FakeStore, armed: list[datetime], recorder: Recorder
):
    recorder.overrides["device/switchMode"] = httpx.Response(
        400, json={"status": 400, "message": "refused"}
    )

    with pytest.raises(HomeAssistantError):
        await manager.async_clear()

    assert manager.active is not None
    assert store.data is not None
    assert armed


async def test_clear_restores_only_the_reserve_on_a_fresh_read(
    manager: OverrideManager, store: FakeStore, recorder: Recorder
):
    changed_during_override = MODE | {
        "selfConsumptioinReserveSoc": "86",
        "allowChargingXiaGrid": "0",
    }
    recorder.overrides["device/getSwitchMode"] = httpx.Response(
        200, json={"status": 200, "data": changed_during_override}
    )

    await manager.async_clear()

    body = recorder.body("device/switchMode")
    assert body["selfConsumptioinReserveSoc"] == "20"
    assert body["allowChargingXiaGrid"] == "0"
    assert manager.active is None
    assert store.data is None

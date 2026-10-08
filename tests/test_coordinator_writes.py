from __future__ import annotations

import asyncio

import pytest

from custom_components.epcube.coordinator import EpCubeCoordinator
from epcube_api import ModeConfig

from .conftest import Recorder


def _mode_reads(recorder: Recorder) -> int:
    return sum(r.url.path.endswith("getSwitchMode") for r in recorder.requests)


async def test_each_write_reads_the_mode_fresh_and_refreshes(
    coordinator: EpCubeCoordinator, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
):
    before = _mode_reads(recorder)
    refreshed: list[int] = []

    async def refresh() -> None:
        refreshed.append(_mode_reads(recorder))

    async def write(config: ModeConfig) -> None:
        pass

    monkeypatch.setattr(coordinator, "async_refresh", refresh)
    await coordinator.async_write(write)
    await coordinator.async_write(write)

    assert _mode_reads(recorder) == before + 2
    assert refreshed == [before + 1, before + 2]


async def test_a_second_write_reads_only_after_the_first_finishes(
    coordinator: EpCubeCoordinator, recorder: Recorder
):
    before = _mode_reads(recorder)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def first(config: ModeConfig) -> None:
        entered.set()
        await release.wait()

    async def second(config: ModeConfig) -> None:
        pass

    task1 = asyncio.create_task(coordinator.async_write(first))
    await entered.wait()
    task2 = asyncio.create_task(coordinator.async_write(second))
    await asyncio.sleep(0.01)

    assert _mode_reads(recorder) == before + 1
    release.set()
    await asyncio.gather(task1, task2)
    assert _mode_reads(recorder) == before + 2

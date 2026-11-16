import asyncio

import pytest

from custom_components.epcube.coordinator import EpCubeCoordinator
from epcube_api import EpCubeAsyncClient
from tests.conftest import SN


@pytest.fixture
async def coordinator(client: EpCubeAsyncClient) -> EpCubeCoordinator:
    coordinator = object.__new__(EpCubeCoordinator)
    coordinator.client = client
    coordinator.data = await client.snapshot(
        SN, include_config=False, include_totals=False, include_series=False
    )
    coordinator._write_lock = asyncio.Lock()

    async def refresh() -> None:
        pass

    coordinator.async_refresh = refresh
    return coordinator

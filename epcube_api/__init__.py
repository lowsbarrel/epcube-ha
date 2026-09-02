"""Client for the EP Cube energy storage cloud API.

The API is undocumented - the one the iOS and Android apps talk to. Everything
here was established by reading the app's compiled routes and exercising them
against a real system; `docs/api-endpoints.md` records what was found and how.

```python
import asyncio
from epcube_api import EpCubeAsyncClient


async def main() -> None:
    async with EpCubeAsyncClient(region="EU", token="…") as client:
        snap = await client.snapshot()
        print(snap.summary_line())


asyncio.run(main())
```

Two things about this API are worth knowing before writing against it:

* **`device/switchMode` resets every field the payload omits.** Sending a partial
  body silently wipes the tariff calendar and the reserve levels. This is why
  writes take a `SwitchModeRequest` built from a fresh read, not a dict.
* **US and JP report errors as HTTP 200** with the real code in the body. The
  transport checks both layers, so an expired token raises rather than looking
  like an empty success.
"""

from .auth import solve_challenge
from .client import EpCubeAsyncClient
from .const import BASE_URLS, USER_AGENT, DayType, Region, Scope, SystemStatus, WorkMode
from .exceptions import (
    EpCubeAPIError,
    EpCubeAuthError,
    EpCubeCaptchaError,
    EpCubeConnectionError,
    EpCubeError,
    EpCubeForbiddenError,
    EpCubeLoginError,
    EpCubeNotFoundError,
    EpCubeRateLimitError,
    EpCubeResponseError,
    EpCubeServerError,
    EpCubeTimeoutError,
)
from .models import (
    Account,
    DeviceDetail,
    DeviceSummary,
    EnergySeries,
    EnergyTotals,
    LiveSnapshot,
    ModeConfig,
    NetworkInfo,
    OutageEvent,
    PvString,
    PvStrings,
    SeriesPoint,
    SeriesReading,
    SwitchModeRequest,
    TouWindow,
    Warranty,
)
from .models.snapshot import Snapshot
from .registry import ROUTES, Route

__version__ = "0.1.0"

__all__ = [
    "BASE_URLS",
    "ROUTES",
    "USER_AGENT",
    "Account",
    "DayType",
    "DeviceDetail",
    "DeviceSummary",
    "EnergySeries",
    "EnergyTotals",
    "EpCubeAPIError",
    "EpCubeAsyncClient",
    "EpCubeAuthError",
    "EpCubeCaptchaError",
    "EpCubeConnectionError",
    "EpCubeError",
    "EpCubeForbiddenError",
    "EpCubeLoginError",
    "EpCubeNotFoundError",
    "EpCubeRateLimitError",
    "EpCubeResponseError",
    "EpCubeServerError",
    "EpCubeTimeoutError",
    "LiveSnapshot",
    "ModeConfig",
    "NetworkInfo",
    "OutageEvent",
    "PvString",
    "PvStrings",
    "Region",
    "Route",
    "Scope",
    "SeriesPoint",
    "SeriesReading",
    "Snapshot",
    "SwitchModeRequest",
    "SystemStatus",
    "TouWindow",
    "Warranty",
    "WorkMode",
    "__version__",
    "solve_challenge",
]

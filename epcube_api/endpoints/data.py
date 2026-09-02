"""Energy history - the two `queryData*` routes.

`totals()` returns one aggregate per call. `series()` returns a curve, and is
what the mobile app's graphs are drawn from: at `Scope.DAY` it yields a reading
every five minutes since midnight, including battery power, which nothing else
in the API reports directly.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..const import Scope
from ..models import EnergySeries, EnergyTotals
from .base import EndpointGroup, parse_model


class DataEndpoints(EndpointGroup):
    """Aggregates and time series."""

    async def totals(
        self,
        dev_id: str,
        scope: Scope | int = Scope.DAY,
        when: date | None = None,
    ) -> EnergyTotals:
        """One aggregate for a window.

        `when` is formatted to match the scope automatically - passing a full
        date with `Scope.YEAR` is a server-side 500, not a validation error.
        """
        scope = Scope(scope)
        return await self._get(
            "device/queryDataElectricityV2",
            parse_model(EnergyTotals),
            devId=dev_id,
            queryDateStr=scope.format_date(when or date.today()),
            scopeType=int(scope),
        )

    async def series(
        self,
        dev_id: str,
        scope: Scope | int = Scope.DAY,
        when: date | None = None,
    ) -> EnergySeries:
        """A curve over the window.

        | scope    | one point covers | typical length |
        | -------- | ---------------- | -------------- |
        | DAY      | five minutes     | midnight → now |
        | MONTH    | one day          | 28-31          |
        | YEAR     | one month        | 12             |
        | LIFETIME | one year         | since install  |

        Points carry `battery_power` and `battery_soc` directly, so a battery
        power reading from here needs none of the subtraction that
        `LiveSnapshot.battery_power` resorts to.
        """
        scope = Scope(scope)
        queried = when or date.today()

        def parse(payload: Any) -> EnergySeries:
            return EnergySeries.from_api(payload, scope=scope, queried=queried)

        return await self._get(
            "device/queryDataGraphV2",
            parse,
            devId=dev_id,
            queryDateStr=scope.format_date(queried),
            scopeType=int(scope),
        )

    async def price_series(
        self,
        dev_id: str,
        scope: Scope | int = Scope.DAY,
        when: date | None = None,
    ) -> Any:
        """Tariff-price curve. Raw shape - returns 404 on accounts without
        dynamic pricing enabled (`dynamic_price_auth` on the device record)."""
        scope = Scope(scope)
        return await self._get(
            "device/queryPriceDataGraphV2",
            devId=dev_id,
            queryDateStr=scope.format_date(when or date.today()),
            scopeType=int(scope),
        )

    async def earnings(self, dev_id: str) -> Any:
        """Configured tariff rates used for the earnings figures. Raw shape."""
        return await self._get("device/getEarningsConfig", devId=dev_id)

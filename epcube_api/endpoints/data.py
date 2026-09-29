from __future__ import annotations

from datetime import date
from typing import Any

from ..const import Scope
from ..models import EnergySeries, EnergyTotals
from .base import EndpointGroup, parse_model


class DataEndpoints(EndpointGroup):
    async def totals(
        self,
        dev_id: str,
        scope: Scope | int = Scope.DAY,
        when: date | None = None,
    ) -> EnergyTotals:
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
        scope = Scope(scope)
        return await self._get(
            "device/queryPriceDataGraphV2",
            devId=dev_id,
            queryDateStr=scope.format_date(when or date.today()),
            scopeType=int(scope),
        )

    async def earnings(self, dev_id: str) -> Any:
        return await self._get("device/getEarningsConfig", devId=dev_id)

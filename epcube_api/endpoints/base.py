from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from ..transport import AsyncTransport, Request

T = TypeVar("T")


class EndpointGroup:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def _call(
        self,
        request: Request,
        parse: Callable[[Any], T] | None = None,
    ) -> Any:
        payload = await self._transport.request(request)
        return payload if parse is None else parse(payload)

    async def _get(
        self,
        path: str,
        parse: Callable[[Any], T] | None = None,
        **params: Any,
    ) -> Any:
        return await self._call(Request("GET", path, params=params), parse)

    async def _post(
        self,
        path: str,
        body: dict[str, Any] | None = None,
        parse: Callable[[Any], T] | None = None,
        **params: Any,
    ) -> Any:
        return await self._call(Request("POST", path, params=params or None, json=body), parse)


def parse_list(model: type[Any]) -> Callable[[Any], list[Any]]:
    def _parse(payload: Any) -> list[Any]:
        if not isinstance(payload, list):
            return []
        return [model.model_validate(item) for item in payload]

    return _parse


def parse_model(model: type[Any]) -> Callable[[Any], Any]:
    def _parse(payload: Any) -> Any:
        return model.model_validate(payload or {})

    return _parse

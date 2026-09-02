"""Machinery shared by every endpoint group.

The client is async-only, deliberately. An earlier draft returned "the value, or
an awaitable of it" so one definition could serve a sync and an async client, but
no single signature is honestly typed for both - `await` either type-checks or it
doesn't. Since the two consumers that matter (Home Assistant and the CLI) are
both happy in an event loop, the surface is async and fully typed rather than
dual-mode and unverifiable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from ..transport import AsyncTransport, Request

T = TypeVar("T")


class EndpointGroup:
    """A namespace of related endpoints bound to one transport."""

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
    """Parser for a route that returns a bare JSON array of one model."""

    def _parse(payload: Any) -> list[Any]:
        if not isinstance(payload, list):
            return []
        return [model.model_validate(item) for item in payload]

    return _parse


def parse_model(model: type[Any]) -> Callable[[Any], Any]:
    """Parser for a route that returns a single object.

    An empty body validates to an all-defaults model rather than raising: several
    routes answer with `data: null` when they have nothing to report, and that is
    a legitimate empty result, not a failure.
    """

    def _parse(payload: Any) -> Any:
        return model.model_validate(payload or {})

    return _parse

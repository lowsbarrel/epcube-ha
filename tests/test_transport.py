"""Transport behaviour: shaping, error mapping, retries and diagnostics."""

from __future__ import annotations

import httpx
import pytest

from epcube_api import (
    EpCubeAsyncClient,
    EpCubeConnectionError,
    EpCubeError,
    EpCubeForbiddenError,
    EpCubeRateLimitError,
    EpCubeResponseError,
    EpCubeServerError,
    EpCubeTimeoutError,
    Region,
)
from epcube_api.exceptions import EpCubeAPIError
from epcube_api.transport import (
    AsyncTransport,
    CallRecord,
    Request,
    TransportConfig,
    normalize_token,
    redact,
)


def transport(handler, **kwargs) -> AsyncTransport:
    config = TransportConfig(region=Region.EU, token="t", backoff=0, **kwargs)
    return AsyncTransport(config, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


# --- helpers ---------------------------------------------------------------


def test_normalize_token_handles_every_shape():
    assert normalize_token("abc") == "Bearer abc"
    assert normalize_token("  abc  ") == "Bearer abc"
    assert normalize_token("Bearer abc") == "Bearer abc"
    assert normalize_token("") is None
    assert normalize_token(None) is None


def test_redact_never_reveals_the_token():
    assert redact(None) == "<none>"
    assert redact("") == "<none>"
    assert redact("Bearer short") == "Bearer ***"
    masked = redact("Bearer " + "x" * 40)
    assert "xxxxxxxxxxxx" not in masked
    assert "40 chars" in masked


def test_request_with_params_merges_without_mutating():
    original = Request("GET", "device/x", params={"a": 1})
    derived = original.with_params(b=2)
    assert original.params == {"a": 1}
    assert derived.params == {"a": 1, "b": 2}
    assert derived.path == "device/x"


def test_call_record_ok_reflects_the_error():
    assert CallRecord("GET", "p", 200, 200, 0.1, 1).ok
    assert not CallRecord("GET", "p", 500, None, 0.1, 1, "boom").ok


# --- request shaping -------------------------------------------------------


async def test_none_params_are_dropped():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": 200, "data": {}})

    await transport(handler).request(Request("GET", "device/x", params={"keep": 1, "drop": None}))
    assert "keep=1" in str(seen[0].url)
    assert "drop" not in str(seen[0].url)


async def test_content_type_only_set_for_a_body():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": 200, "data": {}})

    tr = transport(handler)
    await tr.request(Request("GET", "device/x"))
    await tr.request(Request("POST", "device/x", json={"a": 1}))
    assert "content-type" not in seen[0].headers
    assert seen[1].headers["content-type"] == "application/json"


async def test_token_can_be_replaced_on_a_live_transport():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": 200, "data": {}})

    tr = transport(handler)
    tr.token = "second"
    await tr.request(Request("GET", "device/x"))
    assert seen[0].headers["authorization"] == "Bearer second"


# --- responses -------------------------------------------------------------


async def test_a_bare_list_body_is_returned_as_is():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    assert await transport(handler).request(Request("GET", "device/x")) == [1, 2, 3]


async def test_non_json_is_a_response_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>nope</html>")

    with pytest.raises(EpCubeResponseError, match="expected JSON"):
        await transport(handler).request(Request("GET", "device/x"))


async def test_an_unparsable_body_status_is_ignored():
    """A non-numeric `status` must not blow up the parse."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "weird", "data": {"ok": 1}})

    assert await transport(handler).request(Request("GET", "device/x")) == {"ok": 1}


async def test_403_maps_to_forbidden():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "no"})

    with pytest.raises(EpCubeForbiddenError):
        await transport(handler).request(Request("GET", "device/x"))


async def test_an_unmapped_4xx_is_a_generic_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(418, json={"message": "teapot"})

    with pytest.raises(EpCubeAPIError) as caught:
        await transport(handler).request(Request("GET", "device/x"))
    assert caught.value.http_status == 418


# --- retries ---------------------------------------------------------------


async def test_a_rate_limit_is_retried_then_raised():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"message": "slow down"})

    with pytest.raises(EpCubeRateLimitError):
        await transport(handler, max_retries=3).request(Request("GET", "device/x"))
    assert calls["n"] == 3


async def test_a_server_error_that_recovers_is_not_raised():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"message": "boom"})
        return httpx.Response(200, json={"status": 200, "data": {"recovered": True}})

    result = await transport(handler, max_retries=3).request(Request("GET", "device/x"))
    assert result == {"recovered": True}
    assert calls["n"] == 2


async def test_a_timeout_is_retried_and_reported_as_a_timeout():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(EpCubeTimeoutError, match="timed out"):
        await transport(handler, max_retries=2).request(Request("GET", "device/x"))
    assert calls["n"] == 2


async def test_a_connection_error_is_retried():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(EpCubeConnectionError):
        await transport(handler, max_retries=2).request(Request("GET", "device/x"))


async def test_a_response_error_is_not_retried():
    """Malformed JSON will be malformed again; retrying only wastes time."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text="not json")

    with pytest.raises(EpCubeResponseError):
        await transport(handler, max_retries=3).request(Request("GET", "device/x"))
    assert calls["n"] == 1


async def test_a_body_level_500_is_a_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 500, "message": "Eccezione del server."})

    with pytest.raises(EpCubeServerError):
        await transport(handler, max_retries=1).request(Request("GET", "device/x"))


# --- diagnostics -----------------------------------------------------------


async def test_history_records_success_and_failure():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"status": 200, "data": {}})
        return httpx.Response(404, json={"message": "gone"})

    tr = transport(handler, max_retries=1)
    await tr.request(Request("GET", "device/ok"))
    with pytest.raises(EpCubeError):
        await tr.request(Request("GET", "device/missing"))

    assert [c.ok for c in tr.history] == [True, False]
    assert tr.history[1].error is not None
    assert tr.history[0].attempts == 1


async def test_history_is_capped():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 200, "data": {}})

    tr = transport(handler, history_limit=3)
    for _ in range(6):
        await tr.request(Request("GET", "device/x"))
    assert len(tr.history) == 3


# --- lifecycle -------------------------------------------------------------


async def test_the_client_creates_and_closes_its_own_http_client():
    client = EpCubeAsyncClient(region="EU", token="t")
    assert client._transport.client is not None
    await client.aclose()
    assert client._transport._client is None


async def test_a_supplied_http_client_is_not_closed():
    http = httpx.AsyncClient()
    client = EpCubeAsyncClient(region="EU", token="t", http_client=http)
    await client.aclose()
    assert not http.is_closed
    await http.aclose()


async def test_repr_masks_the_token():
    client = EpCubeAsyncClient(region="EU", token="supersecrettokenvalue")
    assert "supersecret" not in repr(client)
    assert "EU" in repr(client)
    await client.aclose()


async def test_a_body_without_a_status_field_is_accepted():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"fine": True}})

    assert await transport(handler).request(Request("GET", "device/x")) == {"fine": True}

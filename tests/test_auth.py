"""The login flow: solving the slide puzzle, and the retry policy around it."""

from __future__ import annotations

import base64
import json
from io import BytesIO

import httpx
import numpy as np
import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from PIL import Image

from epcube_api import EpCubeAsyncClient, EpCubeCaptchaError, EpCubeError
from epcube_api.auth import async_login, solve_challenge
from epcube_api.exceptions import EpCubeLoginError

SECRET = "0123456789abcdef"  # AES-128 needs exactly 16 bytes
PIECE_X = 120


def _png(array: np.ndarray) -> str:
    buffer = BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def challenge(swap: bool = False) -> dict[str, str]:
    """A synthetic puzzle whose piece sits at a known offset.

    The background is noise so template matching has a unique best match, with
    the piece copied verbatim out of it at PIECE_X.
    """
    rng = np.random.default_rng(seed=1)
    background = rng.integers(0, 255, size=(80, 300, 3), dtype=np.uint8)
    piece = background[0:40, PIECE_X : PIECE_X + 40].copy()
    original, jigsaw = _png(background), _png(piece)
    if swap:
        original, jigsaw = jigsaw, original
    return {
        "originalImageBase64": original,
        "jigsawImageBase64": jigsaw,
        "secretKey": SECRET,
        "token": "challenge-token",
    }


def decrypt(blob: str) -> str:
    cipher = AES.new(SECRET.encode(), AES.MODE_ECB)
    return unpad(cipher.decrypt(base64.b64decode(blob)), AES.block_size).decode()


# --- the solver ------------------------------------------------------------


def test_solve_finds_the_offset_and_encrypts_both_blobs():
    solution = solve_challenge(challenge())

    assert solution.x == pytest.approx(PIECE_X, abs=2)
    assert solution.confidence > 0.9
    assert solution.token == "challenge-token"

    point = json.loads(decrypt(solution.point_json))
    assert point["x"] == pytest.approx(PIECE_X, abs=2)
    assert point["y"] == 5.0

    prefix, _, payload = decrypt(solution.verification).partition("---")
    assert prefix == "challenge-token"
    assert json.loads(payload)["y"] == 5.0


def test_solve_handles_the_images_arriving_swapped():
    """matchTemplate needs the smaller image as the template."""
    solution = solve_challenge(challenge(swap=True))
    assert solution.x == pytest.approx(PIECE_X, abs=2)


@pytest.mark.parametrize(
    "missing", ["originalImageBase64", "jigsawImageBase64", "secretKey", "token"]
)
def test_solve_rejects_an_incomplete_challenge(missing):
    data = challenge()
    data[missing] = ""
    with pytest.raises(EpCubeCaptchaError, match="missing"):
        solve_challenge(data)


# --- the flow --------------------------------------------------------------


class Login:
    """Scripts the three-call login sequence."""

    def __init__(self, *, accept_after: int = 1, token: str | None = "issued-token") -> None:
        self.accept_after = accept_after
        self.token = token
        self.attempts = 0
        self.paths: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.split("/api/", 1)[-1]
        self.paths.append(path)
        if path == "open/common/captcha/get":
            return httpx.Response(200, json={"status": 200, "data": {"repData": challenge()}})
        if path == "open/common/captcha/check":
            self.attempts += 1
            accepted = self.attempts >= self.accept_after
            return httpx.Response(
                200, json={"status": 200, "data": {"repData": {"result": accepted}}}
            )
        if path == "open/common/login":
            body = {} if self.token is None else {"token": self.token}
            return httpx.Response(200, json={"status": 200, "data": body})
        return httpx.Response(404, json={"message": "no"})


async def run_login(script: Login, **kwargs) -> str:
    http = httpx.AsyncClient(transport=httpx.MockTransport(script.handler))
    async with EpCubeAsyncClient(region="EU", http_client=http) as client:
        try:
            return await async_login(client, "a@b.c", "pw", **kwargs)
        finally:
            await http.aclose()


async def test_login_returns_the_token():
    assert await run_login(Login()) == "issued-token"


async def test_login_stores_the_token_on_the_client():
    script = Login()
    http = httpx.AsyncClient(transport=httpx.MockTransport(script.handler))
    async with EpCubeAsyncClient(region="EU", http_client=http) as client:
        await client.login("a@b.c", "pw")
        assert client.token == "Bearer issued-token"
    await http.aclose()


async def test_login_retries_a_rejected_puzzle():
    messages: list[str] = []
    token = await run_login(Login(accept_after=3), on_attempt=messages.append)
    assert token == "issued-token"
    assert any("rejected" in m for m in messages)
    assert any("accepted" in m for m in messages)


async def test_login_gives_up_after_the_attempt_budget():
    with pytest.raises(EpCubeCaptchaError, match="gave up after 2"):
        await run_login(Login(accept_after=99), attempts=2)


async def test_bad_credentials_are_not_retried():
    script = Login(token=None)
    with pytest.raises(EpCubeLoginError, match="credentials rejected"):
        await run_login(script, attempts=5)
    assert script.paths.count("open/common/login") == 1


async def test_a_malformed_challenge_response_is_retried_then_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 200, "data": {"nope": True}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    messages: list[str] = []
    async with EpCubeAsyncClient(region="EU", http_client=http) as client:
        with pytest.raises(EpCubeCaptchaError):
            await async_login(client, "a", "b", attempts=2, on_attempt=messages.append)
    assert any("failed" in m for m in messages)
    await http.aclose()


async def test_a_non_dict_challenge_payload_is_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 200, "data": ["unexpected"]})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with EpCubeAsyncClient(region="EU", http_client=http) as client:
        with pytest.raises(EpCubeCaptchaError):
            await async_login(client, "a", "b", attempts=1)
    await http.aclose()


async def test_missing_solver_dependencies_are_reported_clearly(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "cv2":
            raise ImportError("no cv2 here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(EpCubeError, match="login extra"):
        solve_challenge(challenge())

"""Sign-in: solving the slide-puzzle CAPTCHA that guards `open/common/login`.

The login endpoint will not accept credentials on their own. It first issues a
challenge - a background image with a puzzle-piece-shaped hole, plus the piece -
and expects the horizontal offset where the piece fits, AES-ECB encrypted under
a per-challenge key. Only then does it exchange credentials for a token.

The offset is found by template matching, which is fast but not always exact, so
every entry point retries. The heavy dependencies (OpenCV, NumPy, Pillow,
PyCryptodome) are imported lazily and declared as the `login` extra, because a
caller that already has a token needs none of them.
"""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .exceptions import EpCubeCaptchaError, EpCubeError, EpCubeLoginError

if TYPE_CHECKING:
    from .client import EpCubeAsyncClient

# The piece only ever slides horizontally, so the y coordinate is a constant the
# server does not actually verify.
_FIXED_Y = 5.0


@dataclass(slots=True)
class Solution:
    """A solved challenge, ready to submit."""

    client_uid: str
    token: str
    point_json: str
    """The encrypted offset, for `captcha/check`."""
    verification: str
    """The encrypted `token---point` blob, for `login`."""
    confidence: float
    x: float


def _require_dependencies() -> tuple[Any, Any, Any, Any, Any]:
    try:
        import cv2
        import numpy
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise EpCubeError(
            "signing in needs the login extra: uv sync --extra login "
            "(OpenCV, NumPy, Pillow, PyCryptodome)"
        ) from exc
    return cv2, numpy, AES, pad, Image


def solve_challenge(rep_data: dict[str, Any]) -> Solution:
    """Locate the puzzle piece and build both encrypted blobs.

    Pure and offline: takes the `repData` from `captcha/get` and returns
    everything the next two calls need.
    """
    cv2, numpy, AES, pad, Image = _require_dependencies()
    from io import BytesIO

    required = ("originalImageBase64", "jigsawImageBase64", "secretKey", "token")
    missing = [key for key in required if not rep_data.get(key)]
    if missing:
        raise EpCubeCaptchaError(f"challenge missing {', '.join(missing)}")

    def decode(field: str) -> Any:
        raw = base64.b64decode(rep_data[field])
        image = Image.open(BytesIO(raw))
        return cv2.cvtColor(numpy.array(image), cv2.COLOR_RGB2BGR)

    background = cv2.cvtColor(decode("originalImageBase64"), cv2.COLOR_BGR2GRAY)
    piece = cv2.cvtColor(decode("jigsawImageBase64"), cv2.COLOR_BGR2GRAY)
    # The two images occasionally arrive the other way round; matchTemplate needs
    # the smaller one as the template.
    if piece.shape[0] > background.shape[0] or piece.shape[1] > background.shape[1]:
        background, piece = piece, background

    match = cv2.matchTemplate(background, piece, cv2.TM_CCOEFF_NORMED)
    _, confidence, _, location = cv2.minMaxLoc(match)
    x = float(location[0])

    secret_key: str = rep_data["secretKey"]
    challenge_token: str = rep_data["token"]

    def encrypt(plaintext: bytes) -> str:
        cipher = AES.new(secret_key.encode("utf-8"), AES.MODE_ECB)
        return base64.b64encode(cipher.encrypt(pad(plaintext, AES.block_size))).decode()

    point = json.dumps({"x": x, "y": _FIXED_Y}, separators=(",", ":"))
    return Solution(
        client_uid=str(uuid.uuid4()),
        token=challenge_token,
        point_json=encrypt(point.encode("utf-8")),
        verification=encrypt(f"{challenge_token}---{point}".encode()),
        confidence=float(confidence),
        x=x,
    )


def _rep_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise EpCubeCaptchaError(f"unexpected challenge response: {payload!r}")
    rep = payload.get("repData")
    if not isinstance(rep, dict):
        raise EpCubeCaptchaError("challenge response carried no repData")
    return rep


def _accepted(payload: Any) -> bool:
    return bool(isinstance(payload, dict) and (payload.get("repData") or {}).get("result"))


def _token_from(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("token"):
        return str(payload["token"])
    raise EpCubeLoginError(
        "credentials rejected; check the email, the password, and that the "
        "account really lives on this region's cluster"
    )


async def async_login(
    client: EpCubeAsyncClient,
    username: str,
    password: str,
    *,
    attempts: int = 5,
    on_attempt: Callable[[str], None] | None = None,
) -> str:
    """Solve the CAPTCHA and sign in. Returns the Bearer token."""
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            solution = solve_challenge(_rep_data(await client.public.captcha(str(uuid.uuid4()))))
            accepted = _accepted(
                await client.public.verify_captcha(
                    solution.client_uid, solution.token, solution.point_json
                )
            )
            if on_attempt:
                on_attempt(
                    f"attempt {attempt}/{attempts}: x={solution.x:.0f} "
                    f"confidence={solution.confidence:.2f} -> "
                    f"{'accepted' if accepted else 'rejected'}"
                )
            if not accepted:
                last = EpCubeCaptchaError("puzzle rejected")
                continue
            return _token_from(await client.public.login(username, password, solution.verification))
        except EpCubeLoginError:
            raise
        except (EpCubeError, KeyError, ValueError) as exc:
            last = exc
            if on_attempt:
                on_attempt(f"attempt {attempt}/{attempts} failed: {exc}")
    raise EpCubeCaptchaError(f"gave up after {attempts} attempts: {last}")

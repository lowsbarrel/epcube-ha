"""Account and session routes - `user/*` and the unauthenticated `open/*`."""

from __future__ import annotations

from typing import Any

from ..models import Account
from .base import EndpointGroup, parse_model


class AccountEndpoints(EndpointGroup):
    """The signed-in user, and the self-service routes around the account."""

    async def base(self) -> Account:
        """The signed-in user. `def_dev_sg_sn` is the plant serial everything
        else is keyed on, so this is usually the first call of a session."""
        return await self._get("user/user/base", parse_model(Account))

    async def firmware_info(self) -> Any:
        """`user/user/queryFirmwareInfo`. Raw shape."""
        return await self._get("user/user/queryFirmwareInfo")

    async def service_data(self) -> Any:
        """`user/user/serviceData`. Raw shape."""
        return await self._get("user/user/serviceData")

    async def set_language(self, language: str) -> Any:
        """Change the account language. Affects the localized strings the API
        returns, such as `off_on_grid_hint` and `wifi_status_str`."""
        return await self._post("user/user/saveUserLanguage", body={"language": language})

    async def edit_profile(self, **fields: Any) -> Any:
        """`user/user/editUserInfo`. Field names are passed straight through."""
        return await self._post("user/user/editUserInfo", body=fields)

    async def change_password(self, old_password: str, new_password: str) -> Any:
        """Change the password using the current one."""
        return await self._post(
            "user/user/changePwdByOld",
            body={"oldPassword": old_password, "newPassword": new_password},
        )


class PublicEndpoints(EndpointGroup):
    """`open/*` - reachable without a token.

    The login flow itself lives in `epcube_api.auth`, since solving the CAPTCHA
    needs more than an HTTP call.
    """

    async def captcha(self, client_uid: str) -> Any:
        """Request a slide-puzzle challenge. Returns the images, a per-challenge
        secret key and a challenge token."""
        return await self._call_public("open/common/captcha/get", {"clientUid": client_uid})

    async def verify_captcha(self, client_uid: str, token: str, point_json: str) -> Any:
        """Submit the solved offset, AES-ECB encrypted under the challenge key."""
        return await self._call_public(
            "open/common/captcha/check",
            {"clientUid": client_uid, "token": token, "pointJson": point_json},
        )

    async def login(self, username: str, password: str, captcha_verification: str) -> Any:
        """Exchange credentials plus a solved CAPTCHA for a Bearer token."""
        return await self._call_public(
            "open/common/login",
            {
                "userName": username,
                "password": password,
                "captchaVerification": captcha_verification,
            },
        )

    async def request_email_code(self, email: str) -> Any:
        return await self._call_public("open/common/getEmailCode", {"email": email})

    async def app_version(self) -> Any:
        """Latest published app version. Useful as an unauthenticated reachability
        check for a cluster."""
        return await self._call_public("open/version/update", {})

    async def _call_public(self, path: str, body: dict[str, Any]) -> Any:
        from ..transport import Request

        return await self._call(Request("POST", path, json=body, auth=False))

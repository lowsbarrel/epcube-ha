from __future__ import annotations

from typing import Any

from ..models import Account
from .base import EndpointGroup, parse_model


class AccountEndpoints(EndpointGroup):
    async def base(self) -> Account:
        return await self._get("user/user/base", parse_model(Account))

    async def firmware_info(self) -> Any:
        return await self._get("user/user/queryFirmwareInfo")

    async def service_data(self) -> Any:
        return await self._get("user/user/serviceData")

    async def set_language(self, language: str) -> Any:
        return await self._post("user/user/saveUserLanguage", body={"language": language})

    async def edit_profile(self, **fields: Any) -> Any:
        return await self._post("user/user/editUserInfo", body=fields)

    async def change_password(self, old_password: str, new_password: str) -> Any:
        return await self._post(
            "user/user/changePwdByOld",
            body={"oldPassword": old_password, "newPassword": new_password},
        )


class PublicEndpoints(EndpointGroup):
    async def captcha(self, client_uid: str) -> Any:
        return await self._call_public("open/common/captcha/get", {"clientUid": client_uid})

    async def verify_captcha(self, client_uid: str, token: str, point_json: str) -> Any:
        return await self._call_public(
            "open/common/captcha/check",
            {"clientUid": client_uid, "token": token, "pointJson": point_json},
        )

    async def login(self, username: str, password: str, captcha_verification: str) -> Any:
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
        return await self._call_public("open/version/update", {})

    async def _call_public(self, path: str, body: dict[str, Any]) -> Any:
        from ..transport import Request

        return await self._call(Request("POST", path, json=body, auth=False))

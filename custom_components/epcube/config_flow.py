"""Config and options flow.

Authentication is a Bearer token. It can be minted here from an email and
password, but that needs the CAPTCHA solver (OpenCV and friends) which is an
optional extra and will not be present in a stock Home Assistant install - so
the token path is the primary one and the credentials path is offered only when
the dependencies are importable.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from epcube_api import EpCubeAsyncClient, EpCubeAuthError, EpCubeError, Region

from .const import (
    CONF_DEVICE_ID,
    CONF_ENABLE_SERIES,
    CONF_ENABLE_STATISTICS,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_SN,
    CONF_TOKEN,
    DEFAULT_ENABLE_SERIES,
    DEFAULT_ENABLE_STATISTICS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import EpCubeConfigEntry

_LOGGER = logging.getLogger(__name__)

REGION_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        # Lowercase because hassfest requires translation keys to match
        # [a-z0-9-_]+; Region.parse() accepts either case.
        options=[region.value.lower() for region in Region],
        mode=SelectSelectorMode.DROPDOWN,
        translation_key="region",
    )
)

STEP_TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION, default=Region.EU.value.lower()): REGION_SELECTOR,
        vol.Required(CONF_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
)

STEP_CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION, default=Region.EU.value.lower()): REGION_SELECTOR,
        vol.Required("email"): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
        vol.Required("password"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
)


def _login_available() -> bool:
    """Whether the CAPTCHA solver's dependencies are installed."""
    try:
        import cv2  # noqa: F401
        from Crypto.Cipher import AES  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


class EpCubeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup and reauthentication."""

    VERSION = 1

    def __init__(self) -> None:
        self._region: str = Region.EU.value.lower()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose how to authenticate."""
        if not _login_available():
            return await self.async_step_token()
        return self.async_show_menu(step_id="user", menu_options=["token", "credentials"])

    async def async_step_token(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Set up with a token pasted by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._validate(user_input[CONF_REGION], user_input[CONF_TOKEN], errors)
            if result is not None:
                return result
        return self.async_show_form(step_id="token", data_schema=STEP_TOKEN_SCHEMA, errors=errors)

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Mint a token from an email and password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = EpCubeAsyncClient(
                region=user_input[CONF_REGION],
                http_client=get_async_client(self.hass),
            )
            try:
                token = await client.login(user_input["email"], user_input["password"])
            except EpCubeAuthError:
                errors["base"] = "invalid_auth"
            except EpCubeError as err:
                _LOGGER.debug("login failed: %s", err)
                errors["base"] = "captcha_failed"
            else:
                result = await self._validate(user_input[CONF_REGION], token, errors)
                if result is not None:
                    return result
        return self.async_show_form(
            step_id="credentials", data_schema=STEP_CREDENTIALS_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """A token expired; ask for a new one."""
        self._region = entry_data.get(CONF_REGION, Region.EU.value)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            token = user_input[CONF_TOKEN]
            client = EpCubeAsyncClient(
                region=entry.data[CONF_REGION],
                token=token,
                http_client=get_async_client(self.hass),
            )
            try:
                await client.account.base()
            except EpCubeAuthError:
                errors["base"] = "invalid_auth"
            except EpCubeError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: token})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            description_placeholders={"region": Region.parse(entry.data[CONF_REGION]).value},
            errors=errors,
        )

    async def _validate(
        self, region: str, token: str, errors: dict[str, str]
    ) -> ConfigFlowResult | None:
        """Confirm the token works and discover the system behind it.

        Returns a flow result on success, or None with `errors` populated.
        """
        client = EpCubeAsyncClient(
            region=region, token=token, http_client=get_async_client(self.hass)
        )
        try:
            account = await client.account.base()
            serial = account.def_dev_sg_sn
            if not serial:
                errors["base"] = "no_device"
                return None
            live = await client.device.home_info(serial)
        except EpCubeAuthError:
            # Region mismatches surface here too, and look identical to an
            # expired token, so the message names both possibilities.
            errors["base"] = "invalid_auth"
            return None
        except EpCubeError as err:
            _LOGGER.debug("validation failed: %s", err)
            errors["base"] = "cannot_connect"
            return None

        await self.async_set_unique_id(serial)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"EP Cube {serial[-6:]}",
            data={
                CONF_REGION: region,
                CONF_TOKEN: token,
                CONF_SN: serial,
                CONF_DEVICE_ID: live.dev_id,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: EpCubeConfigEntry) -> OptionsFlow:
        return EpCubeOptionsFlow()


class EpCubeOptionsFlow(OptionsFlow):
    """Polling interval and which optional reads to include."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=5,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_ENABLE_SERIES,
                        default=options.get(CONF_ENABLE_SERIES, DEFAULT_ENABLE_SERIES),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_ENABLE_STATISTICS,
                        default=options.get(CONF_ENABLE_STATISTICS, DEFAULT_ENABLE_STATISTICS),
                    ): BooleanSelector(),
                }
            ),
        )

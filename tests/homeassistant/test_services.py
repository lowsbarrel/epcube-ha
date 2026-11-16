from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from custom_components.epcube.const import DOMAIN
from custom_components.epcube.services import (
    SCHEMA_CHARGE,
    SCHEMA_TOU,
    SERVICE_SET_TOU_SCHEDULE,
    _windows,
)


def _call(data: dict[str, Any]) -> ServiceCall:
    return ServiceCall(cast(HomeAssistant, None), DOMAIN, SERVICE_SET_TOU_SCHEDULE, data)


def test_a_zero_duration_is_rejected():
    with pytest.raises(vol.Invalid):
        SCHEMA_CHARGE({"device_id": "dev", "target_soc": 50, "duration": timedelta(0)})


def test_a_null_window_list_leaves_the_calendar_unchanged():
    validated = SCHEMA_TOU({"device_id": "dev", "peak": None})
    assert _windows(_call(validated), "peak") is None


@pytest.mark.parametrize(
    "window",
    [
        {"start": 720, "end": 1080, "price": 0.3},  # YAML reads unquoted 12:00 as 720
        {"start": "08:00", "end": "12:00", "price": "abc"},
    ],
)
def test_a_malformed_mapping_window_is_rejected(window: dict[str, Any]):
    with pytest.raises(ServiceValidationError):
        _windows(_call({"peak": [window]}), "peak")


def test_a_mapping_window_is_written_in_the_api_form():
    call = _call({"peak": [{"start": "08:00", "end": "12:00", "price": 0.3}]})
    assert _windows(call, "peak") == ["08:00_12:00_0.3"]

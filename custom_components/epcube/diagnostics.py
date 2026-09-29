from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_SN, CONF_TOKEN
from .coordinator import EpCubeConfigEntry

# The API returns owner PII; redact it so a downloaded file is safe to attach to a report.
REDACT = {
    "token",
    "sn",
    "sg_sn",
    "rtu_sn",
    "sn_items",
    "name",
    "user_id",
    "user_email",
    "install_user_id",
    "install_user_id_multi",
    "eu_distributor_id_multi",
    "create_by",
    "lat",
    "lon",
    "city",
    "mail_code",
    "zip_code",
    "address",
    "address_info",
    "address_ids",
    "country",
    "state",
    "wifi_name",
    "dev_id",
    "id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EpCubeConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    snapshot = coordinator.data
    return {
        "entry": async_redact_data(
            {**entry.data, "options": dict(entry.options)}, {CONF_TOKEN, CONF_SN}
        ),
        "region": coordinator.client.region.value,
        "degraded_sections": snapshot.errors,
        "recent_calls": [
            {
                "path": call.path,
                "http_status": call.http_status,
                "api_status": call.api_status,
                "elapsed": round(call.elapsed, 3),
                "attempts": call.attempts,
                "error": call.error,
            }
            for call in coordinator.client.calls[-25:]
        ],
        "snapshot": async_redact_data(snapshot.model_dump(mode="json"), REDACT),
    }

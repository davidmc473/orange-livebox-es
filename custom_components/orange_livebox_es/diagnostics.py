"""Diagnósticos con redacción de datos sensibles (US8, constitución III)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .api.redact import redact_tree
from .coordinator import LiveboxConfigEntry

TO_REDACT_ENTRY = {CONF_PASSWORD, CONF_USERNAME, "unique_id", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LiveboxConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    normalized = asdict(data)
    normalized.pop("raw", None)
    # Las claves del diccionario de clientes son MAC: se sustituyen por un índice
    normalized["devices"] = [
        redact_tree(device) for device in normalized.pop("devices", {}).values()
    ]
    normalized["access_rules"] = [
        redact_tree(rule) for rule in (normalized.pop("access_rules", None) or {}).values()
    ]
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT_ENTRY),
        "driver": coordinator.client.driver,
        "features": sorted(coordinator.client.features),
        "last_update_success": coordinator.last_update_success,
        "data": redact_tree(normalized),
        "raw": redact_tree(data.raw),
    }

"""Integración Orange Livebox (España) para Home Assistant."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .api import create_client
from .clients import TrackedClients
from .const import CONF_DRIVER, DEFAULT_DRIVER, DOMAIN, PLATFORMS
from .coordinator import LiveboxConfigEntry, LiveboxDataUpdateCoordinator
from .entity import router_device_info
from .services import async_setup_services
from .session import async_get_session

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Acciones de la integración (spec 004)."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LiveboxConfigEntry) -> bool:
    """Configura una entrada (un router)."""
    session = async_get_session(hass)
    client = create_client(
        entry.data.get(CONF_DRIVER, DEFAULT_DRIVER),
        session,
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = LiveboxDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # El router primero: los dispositivos de los clientes cuelgan de él (via_device)
    router = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **router_device_info(coordinator)
    )
    coordinator.clients = TrackedClients(hass, entry, router.id)
    coordinator.clients.async_load()
    entry.async_on_unload(coordinator.async_add_listener(coordinator.clients.async_update))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LiveboxConfigEntry) -> bool:
    """Descarga la entrada y cierra la sesión del router (FR-010)."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.async_logout()
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: LiveboxConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

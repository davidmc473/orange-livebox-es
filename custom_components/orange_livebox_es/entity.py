"""Entidad base ligada al dispositivo router."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import LiveboxError, SessionConflict
from .const import DOMAIN
from .coordinator import LiveboxDataUpdateCoordinator


def router_device_info(coordinator: LiveboxDataUpdateCoordinator) -> DeviceInfo:
    device = coordinator.data.device
    info = DeviceInfo(
        identifiers={(DOMAIN, device.serial_number)},
        manufacturer=device.manufacturer,
        model=device.model,
        model_id=device.model_id,
        name=device.model,
        serial_number=device.serial_number,
        sw_version=device.firmware_version,
        hw_version=device.hardware_version,
        configuration_url=getattr(coordinator.client, "base_url", None),
    )
    if device.mac_address:
        info["connections"] = {(CONNECTION_NETWORK_MAC, device.mac_address.lower())}
    return info


class LiveboxEntity(CoordinatorEntity[LiveboxDataUpdateCoordinator]):
    """Entidad del propio router."""

    _attr_has_entity_name = True

    #: entidades de control: siguen operables mientras HA cede la sesión (spec 003, US12)
    _available_while_yielding = False

    def __init__(self, coordinator: LiveboxDataUpdateCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.device.serial_number}_{key}"
        self._attr_device_info = router_device_info(coordinator)

    @property
    def available(self) -> bool:
        return super().available or (self._available_while_yielding and self.coordinator.yielding)


async def async_run_command(
    coordinator: LiveboxDataUpdateCoordinator,
    func: Callable[..., Awaitable[Any]],
    *args: Any,
) -> None:
    """Ejecuta una orden del router traduciendo los errores a ``HomeAssistantError``.

    Las órdenes recuperan la sesión aunque HA la estuviera cediendo (spec 003, US12).
    """
    try:
        await func(*args)
    except SessionConflict as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="command_session_in_use"
        ) from err
    except LiveboxError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    coordinator.async_end_yield()

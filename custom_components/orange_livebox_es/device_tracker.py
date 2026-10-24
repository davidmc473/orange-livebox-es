"""Rastreadores de presencia de los clientes del router (spec 001 US2, spec 004)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ConnectedDevice, Feature
from .api.schedule import ALL_ALLOWED, DAYS, ranges_to_hex
from .const import CONF_TRACK_NEW_DEVICES, DEFAULT_TRACK_NEW_DEVICES, DOMAIN
from .coordinator import LiveboxConfigEntry, LiveboxDataUpdateCoordinator
from .entity import async_run_command

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LiveboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Un tracker por cliente gestionado (ver ``clients.TrackedClients``)."""
    coordinator = entry.runtime_data
    enable_new = entry.options.get(CONF_TRACK_NEW_DEVICES, DEFAULT_TRACK_NEW_DEVICES)

    @callback
    def _async_add(macs: list[str]) -> None:
        async_add_entities(LiveboxDeviceTracker(coordinator, mac, enable_new) for mac in macs)

    _async_add(coordinator.clients.macs)
    entry.async_on_unload(coordinator.clients.async_add_listener(_async_add))


class LiveboxDeviceTracker(CoordinatorEntity[LiveboxDataUpdateCoordinator], ScannerEntity):
    """Presencia de un cliente según la tabla del router."""

    _attr_translation_key = "client"

    def __init__(
        self, coordinator: LiveboxDataUpdateCoordinator, mac: str, enabled_default: bool
    ) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = format_mac(mac)
        self._enabled_default = enabled_default
        device = self._device
        self._attr_name = (device.name if device else None) or mac

    @property
    def _device(self) -> ConnectedDevice | None:
        return self.coordinator.data.devices.get(self._mac)

    @property
    def entity_registry_enabled_default(self) -> bool:
        # La integración registra el dispositivo de cada cliente, así que la regla de HA
        # (habilitar si la MAC ya es conocida) siempre se cumpliría: manda la opción.
        return self._enabled_default

    @property
    def mac_address(self) -> str:
        return self._mac

    @property
    def is_connected(self) -> bool:
        device = self._device
        return bool(device and device.connected)

    @property
    def ip_address(self) -> str | None:
        device = self._device
        return device.ip if device else None

    @property
    def hostname(self) -> str | None:
        # HA usa este valor como nombre del dispositivo: se prefiere el nombre que
        # muestra el router (personalizado en su web) al hostname DHCP.
        device = self._device
        return (device.name or device.hostname) if device else None

    @property
    def icon(self) -> str:
        device = self._device
        if device is None or not device.connected:
            return "mdi:lan-disconnect"
        return "mdi:wifi" if device.connection.is_wifi else "mdi:lan-connect"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        device = self._device
        if device is None:
            return None
        attrs: dict[str, Any] = {
            "connection": device.connection.value,
            "interface": device.interface,
            "address_source": device.address_source,
            "last_seen": device.last_seen,
        }
        if device.connection.is_wifi:
            attrs["ssid"] = device.ssid
            attrs["signal_strength"] = device.signal_strength
        if device.link_rate_mbps:
            attrs["link_rate_mbps"] = device.link_rate_mbps
        if device.vendor_class:
            attrs["vendor_class"] = device.vendor_class
        return attrs

    # --- acciones (spec 004) ------------------------------------------------------------
    @property
    def _access_mac(self) -> str:
        device = self._device
        return (device.access_mac if device else None) or self._mac

    def _require(self, feature: Feature) -> None:
        if feature not in self.coordinator.client.features:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="feature_not_supported"
            )

    async def async_set_router_name(self, name: str) -> None:
        """Acción ``set_device_name``: nombre del cliente en el router."""
        self._require(Feature.DEVICE_RENAME)
        await async_run_command(
            self.coordinator, self.coordinator.client.async_set_device_name, self._access_mac, name
        )
        await self.coordinator.async_request_refresh()

    async def async_set_access_schedule(self, **days: str) -> None:
        """Acción ``set_access_schedule``: franjas permitidas por día (spec 004, US14)."""
        self._require(Feature.DEVICE_ACCESS)
        try:
            schedule = [ranges_to_hex(days[day]) if day in days else ALL_ALLOWED for day in DAYS]
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_schedule",
                translation_placeholders={"error": str(err)},
            ) from err
        if all(day == ALL_ALLOWED for day in schedule):
            schedule_or_none: list[str] | None = None  # sin restricción: se elimina la regla
        else:
            schedule_or_none = schedule
        await async_run_command(
            self.coordinator,
            self.coordinator.client.async_set_device_access,
            self._access_mac,
            schedule_or_none,
        )
        await self.coordinator.async_request_refresh()

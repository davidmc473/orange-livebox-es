"""Clientes de la red que se gestionan en Home Assistant (specs 001 US2 y 004).

El router guarda un histórico enorme (MAC aleatorias, equipos antiguos), así que solo se
gestionan los clientes vistos conectados alguna vez desde que existe la integración; los
ya conocidos se restauran desde el registro de entidades al arrancar.

Cada cliente es un dispositivo de HA (conectado al router con ``via_device``) donde se
agrupan su ``device_tracker`` y su switch de acceso a Internet.
"""

from __future__ import annotations

from collections.abc import Callable
import inspect
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN
from .coordinator import LiveboxConfigEntry

#: sufijo del unique_id del switch de acceso a Internet de un cliente
ACCESS_SWITCH_SUFFIX = "_internet_access"

NewClientsCallback = Callable[[list[str]], None]

#: HA 2026.8+ enlaza con ``via_device_id``; ``via_device`` queda obsoleto (fin en 2027.8)
_HAS_VIA_DEVICE_ID = (
    "via_device_id" in inspect.signature(dr.DeviceRegistry.async_get_or_create).parameters
)


class TrackedClients:
    """Conjunto de MAC gestionadas y aviso a las plataformas cuando aparece una nueva."""

    def __init__(
        self, hass: HomeAssistant, entry: LiveboxConfigEntry, router_device_id: str
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._router_device_id = router_device_id
        self._macs: set[str] = set()
        self._listeners: list[NewClientsCallback] = []

    @property
    def macs(self) -> list[str]:
        return sorted(self._macs)

    @callback
    def async_load(self) -> None:
        """Restaura las MAC de entidades ya registradas y añade las conectadas ahora."""
        for reg_entry in er.async_entries_for_config_entry(
            er.async_get(self._hass), self._entry.entry_id
        ):
            if reg_entry.domain == Platform.DEVICE_TRACKER:
                self._macs.add(reg_entry.unique_id.upper())
            elif reg_entry.domain == Platform.SWITCH and reg_entry.unique_id.endswith(
                ACCESS_SWITCH_SUFFIX
            ):
                self._macs.add(reg_entry.unique_id.removesuffix(ACCESS_SWITCH_SUFFIX).upper())
        self._async_add_connected()
        for mac in self._macs:
            self._async_register_device(mac)

    @callback
    def async_add_listener(self, listener: NewClientsCallback) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def async_update(self) -> None:
        """Llamado en cada actualización del coordinador."""
        new = self._async_add_connected()
        if not new:
            return
        for mac in new:
            self._async_register_device(mac)
        for listener in list(self._listeners):
            listener(new)

    @callback
    def _async_add_connected(self) -> list[str]:
        new = [
            mac
            for mac, device in self._entry.runtime_data.data.devices.items()
            if device.connected and mac not in self._macs
        ]
        self._macs.update(new)
        return new

    @callback
    def _async_register_device(self, mac: str) -> None:
        """Dispositivo de HA del cliente; el tracker se enlaza solo por la MAC."""
        data = self._entry.runtime_data.data
        device = data.devices.get(mac)
        via: dict[str, Any] = (
            {"via_device_id": self._router_device_id}
            if _HAS_VIA_DEVICE_ID
            else {"via_device": (DOMAIN, data.device.serial_number)}
        )
        dr.async_get(self._hass).async_get_or_create(
            config_entry_id=self._entry.entry_id,
            connections={(dr.CONNECTION_NETWORK_MAC, dr.format_mac(mac))},
            name=(device.name if device else None) or mac,
            **via,
        )

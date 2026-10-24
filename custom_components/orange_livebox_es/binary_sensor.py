"""Binary sensors del router (US3, US4, US6)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import LanPort, RouterData, VoipLine
from .api.redact import mask_number
from .coordinator import LiveboxConfigEntry, LiveboxDataUpdateCoordinator
from .entity import LiveboxEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LiveboxBinarySensorEntityDescription(BinarySensorEntityDescription):
    value_fn: Callable[[RouterData], bool | None]
    exists_fn: Callable[[RouterData], bool] = lambda _: True
    attrs_fn: Callable[[RouterData], dict[str, Any]] | None = None


BINARY_SENSORS: tuple[LiveboxBinarySensorEntityDescription, ...] = (
    LiveboxBinarySensorEntityDescription(
        key="internet",
        translation_key="internet",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: d.wan.connected,
    ),
    LiveboxBinarySensorEntityDescription(
        key="optical_link",
        translation_key="optical_link",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda d: d.optical is not None,
        value_fn=lambda d: d.optical.link_up if d.optical else None,
    ),
    # El acceso remoto es un switch desde la spec 002
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LiveboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    data = coordinator.data
    entities: list[BinarySensorEntity] = [
        LiveboxBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if description.exists_fn(data)
    ]
    entities.extend(
        LiveboxVoipLineSensor(coordinator, index) for index in range(len(data.voip_lines))
    )
    entities.extend(LiveboxLanPortSensor(coordinator, port) for port in data.lan_ports)
    async_add_entities(entities)
    _async_remove_stale_lan_ports(hass, entry, {port.index for port in data.lan_ports})


@callback
def _async_remove_stale_lan_ports(
    hass: HomeAssistant, entry: LiveboxConfigEntry, current: set[int]
) -> None:
    """Borra puertos que ya no se exponen (p. ej. «2.5G LAN», que el router no tiene)."""
    registry = er.async_get(hass)
    prefix = f"{entry.runtime_data.data.device.serial_number}_lan_port_"
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            reg_entry.domain == "binary_sensor"
            and reg_entry.unique_id.startswith(prefix)
            and reg_entry.unique_id.removeprefix(prefix).isdigit()
            and int(reg_entry.unique_id.removeprefix(prefix)) not in current
        ):
            registry.async_remove(reg_entry.entity_id)


class LiveboxBinarySensor(LiveboxEntity, BinarySensorEntity):
    entity_description: LiveboxBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: LiveboxDataUpdateCoordinator,
        description: LiveboxBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)


class LiveboxVoipLineSensor(LiveboxEntity, BinarySensorEntity):
    """Registro SIP de una línea telefónica."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "voip_line"

    def __init__(self, coordinator: LiveboxDataUpdateCoordinator, index: int) -> None:
        super().__init__(coordinator, f"voip_line_{index + 1}")
        self._index = index
        self._attr_translation_placeholders = {"line": str(index + 1)}

    @property
    def _line(self) -> VoipLine | None:
        lines = self.coordinator.data.voip_lines
        return lines[self._index] if self._index < len(lines) else None

    @property
    def available(self) -> bool:
        return super().available and self._line is not None

    @property
    def is_on(self) -> bool | None:
        line = self._line
        return line.registered if line else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        line = self._line
        return {"number": mask_number(line.number)} if line else None


class LiveboxLanPortSensor(LiveboxEntity, BinarySensorEntity):
    """Enlace de un puerto Ethernet del router."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "lan_port"

    def __init__(self, coordinator: LiveboxDataUpdateCoordinator, port: LanPort) -> None:
        super().__init__(coordinator, f"lan_port_{port.index}")
        self._port_index = port.index
        self._attr_translation_placeholders = {"port": port.name}

    @property
    def _port(self) -> LanPort | None:
        return next(
            (p for p in self.coordinator.data.lan_ports if p.index == self._port_index), None
        )

    @property
    def available(self) -> bool:
        return super().available and self._port is not None

    @property
    def is_on(self) -> bool | None:
        port = self._port
        return port.link_up if port else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        port = self._port
        if port is None:
            return None
        return {
            "speed_mbps": port.speed_mbps,
            "duplex": None
            if port.full_duplex is None
            else ("full" if port.full_duplex else "half"),
        }

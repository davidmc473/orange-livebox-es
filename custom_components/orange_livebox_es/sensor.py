"""Sensores del router (US3, US4, US5)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .api import RouterData
from .coordinator import LiveboxConfigEntry, LiveboxDataUpdateCoordinator
from .entity import LiveboxEntity

PARALLEL_UPDATES = 0

#: variación mínima para mover un sensor de tipo timestamp derivado de un uptime
_TIMESTAMP_TOLERANCE = timedelta(seconds=90)


def _since(seconds: int | None) -> datetime | None:
    if seconds is None or seconds <= 0:
        return None
    return (dt_util.utcnow() - timedelta(seconds=seconds)).replace(microsecond=0)


def _wifi_count(data: RouterData) -> int:
    return sum(1 for d in data.connected_devices if d.connection.is_wifi)


def _ethernet_count(data: RouterData) -> int:
    return sum(1 for d in data.connected_devices if not d.connection.is_wifi)


@dataclass(frozen=True, kw_only=True)
class LiveboxSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[RouterData], StateType | datetime]
    exists_fn: Callable[[RouterData], bool] = lambda _: True
    attrs_fn: Callable[[RouterData], dict[str, Any]] | None = None


SENSORS: tuple[LiveboxSensorEntityDescription, ...] = (
    # --- WAN ------------------------------------------------------------------------
    LiveboxSensorEntityDescription(
        key="wan_ipv4",
        translation_key="wan_ipv4",
        value_fn=lambda d: d.wan.ipv4,
    ),
    LiveboxSensorEntityDescription(
        key="wan_ipv6",
        translation_key="wan_ipv6",
        # solo si la línea tiene IPv6; si no, sería una entidad siempre «desconocida»
        exists_fn=lambda d: d.wan.ipv6 is not None,
        value_fn=lambda d: d.wan.ipv6,
    ),
    LiveboxSensorEntityDescription(
        key="wan_mode",
        translation_key="wan_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.wan.mode,
    ),
    LiveboxSensorEntityDescription(
        key="dns_servers",
        translation_key="dns_servers",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: ", ".join(d.wan.dns_servers) or None,
    ),
    LiveboxSensorEntityDescription(
        key="wan_connected_since",
        translation_key="wan_connected_since",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _since(d.wan.uptime) if d.wan.connected else None,
    ),
    # --- sistema --------------------------------------------------------------------
    LiveboxSensorEntityDescription(
        key="last_boot",
        translation_key="last_boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _since(d.system.uptime),
    ),
    LiveboxSensorEntityDescription(
        key="cpu_load",
        translation_key="cpu_load",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.system.cpu_load,
    ),
    LiveboxSensorEntityDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda d: d.system.memory_usage,
    ),
    LiveboxSensorEntityDescription(
        key="connected_devices",
        translation_key="connected_devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.connected_devices),
        attrs_fn=lambda d: {"wifi": _wifi_count(d), "ethernet": _ethernet_count(d)},
    ),
    LiveboxSensorEntityDescription(
        key="wifi_devices",
        translation_key="wifi_devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_wifi_count,
    ),
    LiveboxSensorEntityDescription(
        key="ethernet_devices",
        translation_key="ethernet_devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_ethernet_count,
    ),
    LiveboxSensorEntityDescription(
        key="firewall_level",
        translation_key="firewall_level",
        device_class=SensorDeviceClass.ENUM,
        options=["disabled", "low", "medium", "high", "custom"],
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda d: d.firewall_level is not None,
        value_fn=lambda d: d.firewall_level,
    ),
    # --- óptica (FTTH) --------------------------------------------------------------
    LiveboxSensorEntityDescription(
        key="optical_rx_power",
        translation_key="optical_rx_power",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        exists_fn=lambda d: d.optical is not None,
        value_fn=lambda d: d.optical.rx_power if d.optical else None,
    ),
    LiveboxSensorEntityDescription(
        key="optical_tx_power",
        translation_key="optical_tx_power",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        exists_fn=lambda d: d.optical is not None,
        value_fn=lambda d: d.optical.tx_power if d.optical else None,
    ),
    LiveboxSensorEntityDescription(
        key="optical_temperature",
        translation_key="optical_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        exists_fn=lambda d: d.optical is not None,
        value_fn=lambda d: d.optical.temperature if d.optical else None,
    ),
    LiveboxSensorEntityDescription(
        key="optical_voltage",
        translation_key="optical_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        exists_fn=lambda d: d.optical is not None,
        value_fn=lambda d: d.optical.voltage if d.optical else None,
    ),
    LiveboxSensorEntityDescription(
        key="optical_bias_current",
        translation_key="optical_bias_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        exists_fn=lambda d: d.optical is not None,
        value_fn=lambda d: d.optical.bias_current if d.optical else None,
    ),
    LiveboxSensorEntityDescription(
        key="unicast_rx_frames",
        translation_key="unicast_rx_frames",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda d: d.optical is not None,
        value_fn=lambda d: d.optical.unicast_rx_frames if d.optical else None,
    ),
    LiveboxSensorEntityDescription(
        key="unicast_tx_frames",
        translation_key="unicast_tx_frames",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda d: d.optical is not None,
        value_fn=lambda d: d.optical.unicast_tx_frames if d.optical else None,
    ),
    # --- WiFi -----------------------------------------------------------------------
    LiveboxSensorEntityDescription(
        key="wifi_channel_24g",
        translation_key="wifi_channel_24g",
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda d: d.wifi is not None,
        value_fn=lambda d: d.wifi.channel_24g if d.wifi else None,
    ),
    LiveboxSensorEntityDescription(
        key="wifi_channel_5g",
        translation_key="wifi_channel_5g",
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda d: d.wifi is not None,
        value_fn=lambda d: d.wifi.channel_5g if d.wifi else None,
    ),
    LiveboxSensorEntityDescription(
        key="wifi_ssid",
        translation_key="wifi_ssid",
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda d: d.wifi is not None,
        value_fn=lambda d: (d.wifi.ssid_24g or d.wifi.ssid_5g) if d.wifi else None,
        attrs_fn=lambda d: {"ssid_5g": d.wifi.ssid_5g} if d.wifi else {},
    ),
    LiveboxSensorEntityDescription(
        key="guest_wifi_ssid",
        translation_key="guest_wifi_ssid",
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda d: d.wifi is not None and d.wifi.guest_ssid is not None,
        value_fn=lambda d: d.wifi.guest_ssid if d.wifi else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LiveboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        LiveboxSensor(coordinator, description)
        for description in SENSORS
        if description.exists_fn(coordinator.data)
    )


class LiveboxSensor(LiveboxEntity, SensorEntity):
    """Sensor genérico basado en una descripción."""

    entity_description: LiveboxSensorEntityDescription

    def __init__(
        self,
        coordinator: LiveboxDataUpdateCoordinator,
        description: LiveboxSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._last_timestamp: datetime | None = None

    @property
    def native_value(self) -> StateType | datetime:
        value = self.entity_description.value_fn(self.coordinator.data)
        if self.entity_description.device_class is SensorDeviceClass.TIMESTAMP:
            return self._stable_timestamp(value)
        return value

    def _stable_timestamp(self, value: Any) -> datetime | None:
        """Evita que «último arranque» cambie unos segundos en cada sondeo."""
        if not isinstance(value, datetime):
            self._last_timestamp = None
            return None
        if self._last_timestamp is None or abs(value - self._last_timestamp) > (
            _TIMESTAMP_TOLERANCE
        ):
            self._last_timestamp = value
        return self._last_timestamp

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)

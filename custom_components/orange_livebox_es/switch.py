"""Switches: WiFi, invitados (US5), acceso remoto (US9) y acceso a Internet por cliente (US13)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import time
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AccessMode, AccessRule, Feature, LiveboxClient, RouterData
from .api.schedule import ALL_BLOCKED, DAYS, hex_to_ranges
from .clients import ACCESS_SWITCH_SUFFIX
from .const import ASSUMED_STATE_SECONDS, CONF_TRACK_NEW_DEVICES, DEFAULT_TRACK_NEW_DEVICES
from .coordinator import LiveboxConfigEntry, LiveboxDataUpdateCoordinator
from .entity import LiveboxEntity, async_run_command

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class LiveboxSwitchEntityDescription(SwitchEntityDescription):
    feature: Feature
    value_fn: Callable[[RouterData], bool | None]
    set_fn: Callable[[LiveboxClient, bool], Awaitable[None]]
    attrs_fn: Callable[[RouterData], dict[str, Any]] | None = None


SWITCHES: tuple[LiveboxSwitchEntityDescription, ...] = (
    LiveboxSwitchEntityDescription(
        key="wifi",
        translation_key="wifi",
        entity_category=EntityCategory.CONFIG,
        feature=Feature.WIFI_SWITCH,
        value_fn=lambda d: d.wifi.enabled if d.wifi else None,
        set_fn=lambda client, on: client.async_set_wifi_enabled(on),
    ),
    LiveboxSwitchEntityDescription(
        key="guest_wifi",
        translation_key="guest_wifi",
        entity_category=EntityCategory.CONFIG,
        feature=Feature.GUEST_WIFI_SWITCH,
        value_fn=lambda d: d.wifi.guest_enabled if d.wifi else None,
        set_fn=lambda client, on: client.async_set_guest_wifi_enabled(on),
    ),
    LiveboxSwitchEntityDescription(
        key="remote_access",
        translation_key="remote_access",
        entity_category=EntityCategory.CONFIG,
        feature=Feature.REMOTE_ACCESS_SWITCH,
        value_fn=lambda d: d.remote_access.enabled if d.remote_access else None,
        set_fn=lambda client, on: client.async_set_remote_access_enabled(on),
        attrs_fn=lambda d: {"port": d.remote_access.port} if d.remote_access else {},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LiveboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        LiveboxSwitch(coordinator, description)
        for description in SWITCHES
        if description.feature in coordinator.client.features
        and description.value_fn(coordinator.data) is not None
    )

    # Spec 004: acceso a Internet de cada cliente gestionado
    if (
        Feature.DEVICE_ACCESS not in coordinator.client.features
        or coordinator.data.access_rules is None
    ):
        return
    enable_new = entry.options.get(CONF_TRACK_NEW_DEVICES, DEFAULT_TRACK_NEW_DEVICES)

    @callback
    def _async_add(macs: list[str]) -> None:
        async_add_entities(LiveboxClientAccessSwitch(coordinator, mac, enable_new) for mac in macs)

    _async_add(coordinator.clients.macs)
    entry.async_on_unload(coordinator.clients.async_add_listener(_async_add))


class LiveboxSwitch(LiveboxEntity, SwitchEntity):
    """Switch que replica el botón equivalente de la web del router."""

    entity_description: LiveboxSwitchEntityDescription

    def __init__(
        self,
        coordinator: LiveboxDataUpdateCoordinator,
        description: LiveboxSwitchEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._requested: tuple[bool, float] | None = None

    _available_while_yielding = True

    @property
    def is_on(self) -> bool | None:
        reported = self.entity_description.value_fn(self.coordinator.data)
        if self._requested is not None:
            wanted, since = self._requested
            # El router tarda unos segundos en aplicar; se mantiene el estado pedido
            if reported == wanted or time.monotonic() - since > ASSUMED_STATE_SECONDS:
                self._requested = None
            else:
                return wanted
        return reported

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)

    async def _async_set(self, enabled: bool) -> None:
        await async_run_command(
            self.coordinator, self.entity_description.set_fn, self.coordinator.client, enabled
        )
        self._requested = (enabled, time.monotonic())
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


class LiveboxClientAccessSwitch(CoordinatorEntity[LiveboxDataUpdateCoordinator], SwitchEntity):
    """Acceso a Internet de un cliente (control parental del router, spec 004 US13).

    ``off`` = bloqueado siempre; ``on`` = sin restricción o con horario. Encender elimina la
    regla (y el horario, si lo había), igual que «Siempre permitido» en la web.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "internet_access"

    def __init__(
        self, coordinator: LiveboxDataUpdateCoordinator, mac: str, enabled_default: bool
    ) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{format_mac(mac)}{ACCESS_SWITCH_SUFFIX}"
        self._attr_entity_registry_enabled_default = enabled_default
        self._attr_device_info = DeviceInfo(connections={(CONNECTION_NETWORK_MAC, format_mac(mac))})
        self._requested: tuple[bool, float] | None = None

    @property
    def available(self) -> bool:
        # Como los demás controles, operable mientras HA cede la sesión (spec 003)
        return super().available or self.coordinator.yielding

    @property
    def _access_mac(self) -> str:
        device = self.coordinator.data.devices.get(self._mac)
        return (device.access_mac if device else None) or self._mac

    @property
    def _rule(self) -> AccessRule | None:
        data = self.coordinator.data
        device = data.devices.get(self._mac)
        if device is not None:
            return data.access_rule(device)
        return (data.access_rules or {}).get(self._mac)

    @property
    def is_on(self) -> bool:
        rule = self._rule
        reported = rule is None or rule.mode is not AccessMode.BLOCKED
        if self._requested is not None:
            wanted, since = self._requested
            if reported == wanted or time.monotonic() - since > ASSUMED_STATE_SECONDS:
                self._requested = None
            else:
                return wanted
        return reported

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rule = self._rule
        if rule is None:
            return {"mode": AccessMode.ALLOWED.value}
        attrs: dict[str, Any] = {"mode": rule.mode.value}
        if rule.mode is AccessMode.SCHEDULED:
            attrs["schedule"] = {
                day: hex_to_ranges(value) for day, value in zip(DAYS, rule.schedule, strict=False)
            }
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(None, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set([ALL_BLOCKED] * len(DAYS), False)

    async def _async_set(self, schedule: list[str] | None, allowed: bool) -> None:
        await async_run_command(
            self.coordinator,
            self.coordinator.client.async_set_device_access,
            self._access_mac,
            schedule,
        )
        self._requested = (allowed, time.monotonic())
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

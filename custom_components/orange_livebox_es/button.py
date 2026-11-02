"""Botones del router: reinicio (US7) y prueba del teléfono (spec 008)."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Feature
from .coordinator import LiveboxConfigEntry, LiveboxDataUpdateCoordinator
from .entity import LiveboxEntity, async_run_command

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LiveboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    features = coordinator.client.features
    buttons: list[ButtonEntity] = []
    if Feature.REBOOT in features:
        buttons.append(LiveboxRebootButton(coordinator))
    # Sin línea de voz no hay teléfono que probar
    if Feature.RING_TEST in features and coordinator.data.voip_lines:
        buttons.append(LiveboxRingTestButton(coordinator))
    async_add_entities(buttons)


class LiveboxRebootButton(LiveboxEntity, ButtonEntity):
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "reboot"
    _available_while_yielding = True

    def __init__(self, coordinator: LiveboxDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "reboot")

    async def async_press(self) -> None:
        await async_run_command(self.coordinator, self.coordinator.client.async_reboot)


class LiveboxRingTestButton(LiveboxEntity, ButtonEntity):
    """Hace sonar el teléfono conectado al router, como el botón «test» de su web."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "phone_ring_test"
    _available_while_yielding = True

    def __init__(self, coordinator: LiveboxDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "phone_ring_test")

    async def async_press(self) -> None:
        await async_run_command(self.coordinator, self.coordinator.client.async_ring_test)

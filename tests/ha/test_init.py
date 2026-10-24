"""Tests de setup, entidades, acciones y diagnósticos (T030–T039)."""

from __future__ import annotations

import json

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_HOME, STATE_NOT_HOME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.orange_livebox_es.api import InvalidAuth, LiveboxError, SessionConflict
from custom_components.orange_livebox_es.const import CONF_TRACK_NEW_DEVICES, DOMAIN
from custom_components.orange_livebox_es.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import SERIAL, FakeClient


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id, f"{platform} {unique_id} no registrado"
    return entity_id


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    devices = dr.async_get(hass).async_get_devices(
        identifiers={(DOMAIN, SERIAL)}, config_entry_id=config_entry.entry_id
    )
    assert len(devices) == 1
    device = devices[0]
    assert device.manufacturer == "Arcadyan"
    assert device.model == "Livebox 6"
    assert device.model_id == "ARLTFIBRA6"
    assert device.sw_version == "02.03.01.035D build204"

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert mock_client.calls[-1] == "logout"


async def test_sensors_and_binary_sensors(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)

    def state(platform: str, key: str) -> str:
        return hass.states.get(_entity_id(hass, platform, f"{SERIAL}_{key}")).state

    assert state("binary_sensor", "internet") == STATE_ON
    assert state("binary_sensor", "optical_link") == STATE_ON
    assert state("binary_sensor", "voip_line_1") == STATE_ON
    assert state("sensor", "wan_ipv4") == "203.0.113.10"
    assert state("sensor", "connected_devices") == "5"
    assert state("sensor", "wifi_devices") == "3"
    assert float(state("sensor", "optical_rx_power")) == -18.181
    assert state("sensor", "wifi_channel_5g") == "36"
    assert state("sensor", "last_boot") not in ("unknown", "unavailable")

    voip = hass.states.get(_entity_id(hass, "binary_sensor", f"{SERIAL}_voip_line_1"))
    assert voip.attributes["number"] == "*********123"

    # Spec 002: todas las entidades del router se crean habilitadas
    assert state("binary_sensor", "lan_port_1") == STATE_ON
    assert state("binary_sensor", "lan_port_3") == "off"
    assert state("sensor", "optical_voltage") == "3.28"
    assert state("sensor", "firewall_level") == "medium"
    registry = er.async_get(hass)
    disabled = [
        e.entity_id
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
        if e.disabled_by is not None
    ]
    assert disabled == []
    # sin IPv6 en la línea no se crea la entidad IPv6 WAN
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_wan_ipv6") is None
    # el acceso remoto ya no es un binary_sensor
    assert registry.async_get_entity_id("binary_sensor", DOMAIN, f"{SERIAL}_remote_access") is None


async def test_device_trackers(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    registry = er.async_get(hass)
    trackers = [
        e
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
        if e.domain == "device_tracker"
    ]
    # Solo los clientes online (5), no el histórico offline
    assert len(trackers) == 5
    phone = hass.states.get(_entity_id(hass, "device_tracker", "02:00:00:00:00:02"))
    assert phone.state == STATE_HOME
    assert phone.attributes["ip"] == "192.168.1.21"
    assert phone.attributes["connection"] == "wifi_5ghz"
    assert phone.attributes["signal_strength"] == -55

    # El cliente se desconecta → not_home; uno nuevo aparece → se crea su tracker
    mock_client.data.devices["02:00:00:00:00:02"].connected = False
    mock_client.data.devices["02:00:00:00:00:04"].connected = True
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    phone = hass.states.get(_entity_id(hass, "device_tracker", "02:00:00:00:00:02"))
    assert phone.state == STATE_NOT_HOME
    tv = hass.states.get(_entity_id(hass, "device_tracker", "02:00:00:00:00:04"))
    assert tv.state == STATE_HOME


async def test_trackers_restored_after_reload(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    for device in mock_client.data.devices.values():
        device.connected = False
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    phone = hass.states.get(_entity_id(hass, "device_tracker", "02:00:00:00:00:02"))
    assert phone.state == STATE_NOT_HOME


async def test_new_trackers_disabled_by_option(
    hass: HomeAssistant, mock_client: FakeClient
) -> None:
    from .conftest import ENTRY_DATA

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=SERIAL, data=ENTRY_DATA, options={CONF_TRACK_NEW_DEVICES: False}
    )
    entry.add_to_hass(hass)
    await _setup(hass, entry)
    reg_entry = er.async_get(hass).async_get(
        _entity_id(hass, "device_tracker", "02:00:00:00:00:01")
    )
    assert reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_switches(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    guest = _entity_id(hass, "switch", f"{SERIAL}_guest_wifi")
    wifi = _entity_id(hass, "switch", f"{SERIAL}_wifi")
    assert hass.states.get(guest).state == STATE_OFF
    assert hass.states.get(wifi).state == STATE_ON

    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: guest}, blocking=True)
    await hass.async_block_till_done()
    assert ("guest_wifi", True) in mock_client.calls
    assert hass.states.get(guest).state == STATE_ON

    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: wifi}, blocking=True)
    await hass.async_block_till_done()
    assert ("wifi", False) in mock_client.calls
    assert hass.states.get(wifi).state == STATE_OFF


async def test_remote_access_switch(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    remote = _entity_id(hass, "switch", f"{SERIAL}_remote_access")
    state = hass.states.get(remote)
    assert state.state == STATE_ON
    assert state.attributes["port"] == 20022
    # nunca se exponen las credenciales del acceso remoto
    assert "remoteuser" not in str(state.attributes)

    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: remote}, blocking=True)
    await hass.async_block_till_done()
    assert ("remote_access", False) in mock_client.calls
    assert hass.states.get(remote).state == STATE_OFF


async def test_switch_error_is_reported(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    from homeassistant.exceptions import HomeAssistantError
    import pytest

    await _setup(hass, config_entry)

    async def fail(enabled: bool) -> None:
        raise LiveboxError("rechazado")

    mock_client.async_set_guest_wifi_enabled = fail  # type: ignore[method-assign]
    guest = _entity_id(hass, "switch", f"{SERIAL}_guest_wifi")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: guest}, blocking=True)
    assert hass.states.get(guest).state == STATE_OFF


async def test_reboot_button(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    button = _entity_id(hass, "button", f"{SERIAL}_reboot")
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: button}, blocking=True)
    assert "reboot" in mock_client.calls


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    mock_client.error = InvalidAuth()
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_router_unreachable_retries(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    mock_client.error = LiveboxError("timeout")
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_diagnostics_have_no_secrets(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)
    dump = json.dumps(diagnostics, default=str)
    for secret in (
        "s3cret",
        "SuperSecretWifiKey",
        "GuestSecretKey",
        "RemoteSecret-123",
        "remoteuser",
        "12345670",
        "30303030303030303030",
        "+34900000123",
        "203.0.113.10",
        SERIAL,
        "02:00:00:00:00:0",
        "60:8D:26:00:00:1",  # MAC del router (topología)
        "60:8d:26:00:00:1",
        "laptop-test",
        "Livebox6-TEST",
    ):
        assert secret not in dump, secret
    # pero sigue siendo útil
    assert diagnostics["data"]["optical"]["rx_power"] == -18.181
    assert diagnostics["raw"]["router_status"]["vars"]["hardware_model"] == "ARLTFIBRA6"
    assert len(diagnostics["data"]["devices"]) == 6


async def test_session_conflict_yields_to_web_user(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    """Spec 003: si la web del router expulsa a HA, HA cede la sesión."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    internet = _entity_id(hass, "binary_sensor", f"{SERIAL}_internet")
    guest = _entity_id(hass, "switch", f"{SERIAL}_guest_wifi")

    calls = 0
    original = mock_client.async_get_data

    async def counting():
        nonlocal calls
        calls += 1
        return await original()

    mock_client.async_get_data = counting  # type: ignore[method-assign]
    mock_client.error = SessionConflict("web abierta")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.yielding
    assert hass.states.get(internet).state == "unavailable"
    # los controles siguen operables durante la cesión
    assert hass.states.get(guest).state == STATE_OFF

    # durante la cesión no se contacta con el router
    before = calls
    await coordinator.async_refresh()
    assert calls == before

    # una orden explícita recupera la sesión y termina la cesión
    mock_client.error = None
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: guest}, blocking=True)
    await hass.async_block_till_done()
    assert ("guest_wifi", True) in mock_client.calls
    assert not coordinator.yielding
    assert hass.states.get(internet).state == STATE_ON


async def test_yield_expires(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    mock_client.error = SessionConflict("web abierta")
    await coordinator.async_refresh()
    assert coordinator.yielding
    mock_client.error = None
    now = coordinator._now()
    coordinator._now = lambda: now + coordinator.yield_seconds + 1  # type: ignore[method-assign]
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.last_update_success
    assert not coordinator.yielding


# --- Spec 004: gestión de dispositivos ---------------------------------------------------


async def test_clients_are_devices_with_tracker_and_access_switch(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    router = dev_reg.async_get_devices(
        identifiers={(DOMAIN, SERIAL)}, config_entry_id=config_entry.entry_id
    )[0]
    phone = dev_reg.async_get_devices(
        connections={(dr.CONNECTION_NETWORK_MAC, "02:00:00:00:00:02")},
        config_entry_id=config_entry.entry_id,
    )
    assert len(phone) == 1
    assert phone[0].via_device_id == router.id
    entities = {e.domain for e in er.async_entries_for_device(ent_reg, phone[0].id)}
    assert entities == {"device_tracker", "switch"}


async def test_access_switch_states(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)

    def access(mac: str):
        return hass.states.get(_entity_id(hass, "switch", f"{mac.lower()}_internet_access"))

    assert access("02:00:00:00:00:01").state == STATE_ON
    assert access("02:00:00:00:00:01").attributes["mode"] == "allowed"
    blocked = access("02:00:00:00:00:03")
    assert blocked.state == STATE_OFF and blocked.attributes["mode"] == "blocked"
    scheduled = access("02:00:00:00:00:05")
    assert scheduled.state == STATE_ON
    assert scheduled.attributes["mode"] == "scheduled"
    assert scheduled.attributes["schedule"]["monday"] == "8-16"
    assert scheduled.attributes["schedule"]["sunday"] == "0-24"


async def test_access_switch_block_and_allow(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    laptop = _entity_id(hass, "switch", "02:00:00:00:00:01_internet_access")
    blocked = _entity_id(hass, "switch", "02:00:00:00:00:03_internet_access")
    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: laptop}, blocking=True)
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: blocked}, blocking=True)
    assert ("device_access", "02:00:00:00:00:01", ["000000"] * 7) in mock_client.calls
    assert ("device_access", "02:00:00:00:00:03", None) in mock_client.calls


async def test_service_set_device_name(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    tracker = _entity_id(hass, "device_tracker", "02:00:00:00:00:02")
    await hass.services.async_call(
        DOMAIN, "set_device_name", {ATTR_ENTITY_ID: tracker, "name": "Móvil"}, blocking=True
    )
    assert ("device_name", "02:00:00:00:00:02", "Móvil") in mock_client.calls


async def test_service_set_access_schedule(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    tracker = _entity_id(hass, "device_tracker", "02:00:00:00:00:02")
    await hass.services.async_call(
        DOMAIN,
        "set_access_schedule",
        {ATTR_ENTITY_ID: tracker, "monday": "8-16", "sunday": "-"},
        blocking=True,
    )
    expected = ["00FF00"] + ["FFFFFF"] * 5 + ["000000"]
    assert ("device_access", "02:00:00:00:00:02", expected) in mock_client.calls

    # sin días: se quita la restricción
    await hass.services.async_call(
        DOMAIN, "set_access_schedule", {ATTR_ENTITY_ID: tracker}, blocking=True
    )
    assert ("device_access", "02:00:00:00:00:02", None) in mock_client.calls


async def test_service_set_access_schedule_invalid(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    from homeassistant.exceptions import ServiceValidationError
    import pytest

    await _setup(hass, config_entry)
    tracker = _entity_id(hass, "device_tracker", "02:00:00:00:00:02")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_access_schedule",
            {ATTR_ENTITY_ID: tracker, "monday": "22-8"},
            blocking=True,
        )
    assert not [c for c in mock_client.calls if c[0] == "device_access"]


async def test_stale_lan_port_entity_is_removed(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    """v0.1 creaba «Puerto 2.5G LAN», que el router no tiene: se borra al actualizar."""
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "binary_sensor", DOMAIN, f"{SERIAL}_lan_port_5", config_entry=config_entry
    )
    await _setup(hass, config_entry)
    assert registry.async_get(stale.entity_id) is None
    assert registry.async_get_entity_id("binary_sensor", DOMAIN, f"{SERIAL}_lan_port_4")

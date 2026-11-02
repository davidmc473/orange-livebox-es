"""Tests de setup, entidades, acciones y diagnósticos (T030–T039)."""

from __future__ import annotations

import json

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_HOME,
    STATE_NOT_HOME,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.orange_livebox_es.api import (
    ConnectionType,
    InvalidAuth,
    LiveboxError,
    SessionConflict,
)
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
        if e.disabled_by is not None and e.unique_id.startswith(SERIAL)
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


# --- Spec 007: sensores por dispositivo ---------------------------------------------------

LAPTOP = "02:00:00:00:00:01"  # por cable, 1000 Mbit/s
PHONE = "02:00:00:00:00:02"  # WiFi 5 GHz, -55 dBm, 866 Mbit/s
OFFLINE = "02:00:00:00:00:04"  # visto en el histórico, por cable


def _enable_client_sensor(
    hass: HomeAssistant, entry: MockConfigEntry, mac: str, key: str
) -> er.RegistryEntry:
    """Registra el sensor ya habilitado, como si el usuario lo hubiera activado."""
    return er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"{mac}_{key}", config_entry=entry, disabled_by=None
    )


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


def _client_device(hass: HomeAssistant, entry: MockConfigEntry, mac: str) -> dr.DeviceEntry:
    devices = dr.async_get(hass).async_get_devices(
        connections={(dr.CONNECTION_NETWORK_MAC, mac)}, config_entry_id=entry.entry_id
    )
    assert len(devices) == 1
    return devices[0]


async def test_client_sensors_are_disabled_diagnostics_on_the_client_device(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    ent_reg = er.async_get(hass)
    phone_device = _client_device(hass, config_entry, PHONE)

    for key in ("signal_strength", "link_rate"):
        reg_entry = ent_reg.async_get(_entity_id(hass, "sensor", f"{PHONE}_{key}"))
        assert reg_entry.device_id == phone_device.id
        assert reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert reg_entry.entity_category is EntityCategory.DIAGNOSTIC


async def test_client_sensors_by_connection_type(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, config_entry.entry_id)
    signal = sorted(e.unique_id for e in entries if e.unique_id.endswith("_signal_strength"))
    link = [e.unique_id for e in entries if e.unique_id.endswith("_link_rate")]
    # solo los tres clientes WiFi tienen señal; los cinco conectados, velocidad
    assert signal == [
        "02:00:00:00:00:02_signal_strength",
        "02:00:00:00:00:05_signal_strength",
        "02:00:00:00:00:06_signal_strength",
    ]
    assert len(link) == 5
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{LAPTOP}_signal_strength") is None
    # ni el histórico del router: el cliente nunca visto conectado no tiene sensores
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{OFFLINE}_link_rate") is None


async def test_client_sensor_values_and_units(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    _enable_client_sensor(hass, config_entry, PHONE, "signal_strength")
    _enable_client_sensor(hass, config_entry, PHONE, "link_rate")
    _enable_client_sensor(hass, config_entry, LAPTOP, "link_rate")
    await _setup(hass, config_entry)

    signal = hass.states.get(_entity_id(hass, "sensor", f"{PHONE}_signal_strength"))
    assert signal.state == "-55"
    assert signal.attributes[ATTR_UNIT_OF_MEASUREMENT] == "dBm"
    assert signal.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.SIGNAL_STRENGTH

    rate = hass.states.get(_entity_id(hass, "sensor", f"{PHONE}_link_rate"))
    assert rate.state == "866"
    assert rate.attributes[ATTR_UNIT_OF_MEASUREMENT] == "Mbit/s"
    assert rate.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.DATA_RATE

    wired = hass.states.get(_entity_id(hass, "sensor", f"{LAPTOP}_link_rate"))
    assert wired.state == "1000"


async def test_client_sensors_ignore_stale_values_when_disconnected(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    """El router conserva la última señal de un cliente desconectado: no debe mostrarse."""
    _enable_client_sensor(hass, config_entry, PHONE, "signal_strength")
    _enable_client_sensor(hass, config_entry, PHONE, "link_rate")
    await _setup(hass, config_entry)
    signal = _entity_id(hass, "sensor", f"{PHONE}_signal_strength")
    rate = _entity_id(hass, "sensor", f"{PHONE}_link_rate")

    phone = mock_client.data.devices[PHONE]
    phone.connected = False
    assert phone.signal_strength == -55  # el dato sigue ahí
    await _refresh(hass, config_entry)
    assert hass.states.get(signal).state == STATE_UNKNOWN
    assert hass.states.get(rate).state == STATE_UNKNOWN

    phone.connected = True
    phone.signal_strength = -61
    await _refresh(hass, config_entry)
    assert hass.states.get(signal).state == "-61"
    assert hass.states.get(rate).state == "866"


async def test_client_sensors_unavailable_while_yielding_session(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    _enable_client_sensor(hass, config_entry, PHONE, "signal_strength")
    await _setup(hass, config_entry)
    signal = _entity_id(hass, "sensor", f"{PHONE}_signal_strength")

    mock_client.error = SessionConflict("web abierta")
    await _refresh(hass, config_entry)
    assert hass.states.get(signal).state == STATE_UNAVAILABLE


async def test_signal_sensor_created_when_client_moves_to_wifi(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_client: FakeClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _setup(hass, config_entry)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{LAPTOP}_signal_strength") is None

    laptop = mock_client.data.devices[LAPTOP]
    laptop.connection = ConnectionType.WIFI_5GHZ
    await _refresh(hass, config_entry)
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{LAPTOP}_signal_strength")

    # los ciclos siguientes no vuelven a añadirlo
    await _refresh(hass, config_entry)
    assert "does not generate unique IDs" not in caplog.text


async def test_new_client_gets_its_sensors(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    mock_client.data.devices[OFFLINE].connected = True
    await _refresh(hass, config_entry)

    reg_entry = er.async_get(hass).async_get(_entity_id(hass, "sensor", f"{OFFLINE}_link_rate"))
    assert reg_entry.device_id == _client_device(hass, config_entry, OFFLINE).id


async def test_client_sensor_survives_reload_while_client_is_away(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    """Un móvil desconectado puede figurar «por cable» en el router: conserva su sensor."""
    reg_entry = _enable_client_sensor(hass, config_entry, PHONE, "signal_strength")
    await _setup(hass, config_entry)

    phone = mock_client.data.devices[PHONE]
    phone.connected = False
    phone.connection = ConnectionType.ETHERNET
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(reg_entry.entity_id)
    assert state.state == STATE_UNKNOWN
    assert not state.attributes.get("restored")


# --- Spec 008: hacer sonar el teléfono ----------------------------------------------------


async def test_ring_button_presses_ring_test(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    button = _entity_id(hass, "button", f"{SERIAL}_phone_ring_test")
    assert er.async_get(hass).async_get(button).entity_category is EntityCategory.DIAGNOSTIC
    assert "ring_test" not in mock_client.calls

    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: button}, blocking=True)
    assert mock_client.calls.count("ring_test") == 1


async def test_ring_button_needs_a_phone_line(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    mock_client.data.voip_lines.clear()
    await _setup(hass, config_entry)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("button", DOMAIN, f"{SERIAL}_phone_ring_test") is None
    assert registry.async_get_entity_id("button", DOMAIN, f"{SERIAL}_reboot")


async def test_ring_button_error_is_reported(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    from homeassistant.exceptions import HomeAssistantError

    await _setup(hass, config_entry)

    async def fail() -> None:
        raise LiveboxError("rechazado")

    mock_client.async_ring_test = fail  # type: ignore[method-assign]
    button = _entity_id(hass, "button", f"{SERIAL}_phone_ring_test")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: button}, blocking=True)


async def test_ring_button_works_while_yielding_session(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    button = _entity_id(hass, "button", f"{SERIAL}_phone_ring_test")

    mock_client.error = SessionConflict("web abierta")
    await _refresh(hass, config_entry)
    assert coordinator.yielding
    assert hass.states.get(button).state != STATE_UNAVAILABLE

    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: button}, blocking=True)
    assert "ring_test" in mock_client.calls
    assert not coordinator.yielding

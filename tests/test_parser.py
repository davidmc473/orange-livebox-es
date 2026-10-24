"""Tests de normalización CGI → RouterData (T023)."""

from __future__ import annotations

import pytest

from custom_components.orange_livebox_es.api.arcadyan.parser import (
    build_router_data,
    parse_speed,
)
from custom_components.orange_livebox_es.api.exceptions import ParseError
from custom_components.orange_livebox_es.api.jsparse import JsDocument, parse_js
from custom_components.orange_livebox_es.api.models import ConnectionType


def test_device_and_system(fixture_docs: dict) -> None:
    data = build_router_data(fixture_docs)
    assert data.device.serial_number == "ARLT00TEST01"
    assert data.device.model == "Livebox 6"
    assert data.device.model_id == "ARLTFIBRA6"
    assert data.device.manufacturer == "Arcadyan"
    assert data.device.firmware_version == "02.03.01.035D build204"
    assert data.device.mac_address == "60:8D:26:00:00:17"
    assert data.system.uptime == 86400
    assert data.system.cpu_load == 12.0
    assert data.system.memory_usage == 62.5


def test_wan(fixture_docs: dict) -> None:
    wan = build_router_data(fixture_docs).wan
    assert wan.connected is True
    assert wan.mode == "GPON"
    assert wan.ipv4 == "203.0.113.10"
    assert wan.ipv6 is None
    assert wan.dns_servers == ["62.36.225.150", "62.37.228.20"]  # sin la IP del router
    assert wan.uptime == 3600


def test_wan_down_when_link_down(fixture_docs: dict) -> None:
    fixture_docs["infoInternet"] = parse_js("var wan_link_status=[['down','',''],null];")
    assert build_router_data(fixture_docs).wan.connected is False


def test_wan_disconnected_without_ip(fixture_docs: dict) -> None:
    fixture_docs["info"].vars["defroute_wan_ip"] = "0.0.0.0"
    fixture_docs["infoInternet"] = JsDocument()
    assert build_router_data(fixture_docs).wan.connected is False


def test_optical(fixture_docs: dict) -> None:
    optical = build_router_data(fixture_docs).optical
    assert optical is not None
    assert optical.link_up is True
    assert optical.rx_power == -18.181
    assert optical.tx_power == 2.439
    assert optical.temperature == 46.785
    assert optical.voltage == 3.28
    assert optical.bias_current == 15.0
    assert optical.unicast_rx_frames == 528708348


def test_lan_ports(fixture_docs: dict) -> None:
    ports = build_router_data(fixture_docs).lan_ports
    # Solo los 4 puertos que muestra la web: el firmware declara también «2.5G LAN» y un
    # 6.º puerto que el Livebox 6 español no tiene físicamente
    assert [p.name for p in ports] == ["LAN1", "LAN2", "LAN3", "LAN4"]
    assert ports[1].speed_mbps == 100 and ports[1].full_duplex is False
    assert ports[2].link_up is False and ports[2].speed_mbps is None


def test_wifi(fixture_docs: dict) -> None:
    wifi = build_router_data(fixture_docs).wifi
    assert wifi is not None
    assert wifi.enabled is True
    assert wifi.ssid_24g == "Livebox6-TEST"
    assert wifi.channel_24g == 6 and wifi.channel_5g == 36
    assert wifi.schedule_enabled is True
    assert wifi.guest_enabled is False
    assert wifi.guest_ssid == "Invitado-TEST"


def test_voip_remote_firewall(fixture_docs: dict) -> None:
    data = build_router_data(fixture_docs)
    assert len(data.voip_lines) == 1
    assert data.voip_lines[0].number == "+34900000123"
    assert data.voip_lines[0].registered is True
    assert data.remote_access is not None
    assert data.remote_access.enabled is True and data.remote_access.port == 20022
    assert data.firewall_level == "medium"


def test_devices_merge_and_names(fixture_docs: dict) -> None:
    devices = build_router_data(fixture_docs).devices
    # 6 MAC válidas en online_client + 1 estación online que no aparece allí
    assert set(devices) == {
        "02:00:00:00:00:01",
        "02:00:00:00:00:02",
        "02:00:00:00:00:03",
        "02:00:00:00:00:04",
        "02:00:00:00:00:05",
        "02:00:00:00:00:06",
    }
    laptop = devices["02:00:00:00:00:01"]
    assert laptop.connected and laptop.connection is ConnectionType.ETHERNET
    assert laptop.link_rate_mbps == 1000 and laptop.signal_strength is None
    assert laptop.vendor_class == "MSFT 5.0"

    phone = devices["02:00:00:00:00:02"]
    assert phone.connection is ConnectionType.WIFI_5GHZ  # gana la estación online
    assert phone.signal_strength == -55 and phone.link_rate_mbps == 866
    assert phone.ssid == "Livebox6-TEST"
    assert phone.ipv6 == "2001:db8::21"

    merged = devices["02:00:00:00:00:03"]
    assert merged.connected is True and merged.name == "new-name"
    assert merged.address_source == "DHCP" and merged.link_rate_mbps == 100

    offline = devices["02:00:00:00:00:04"]
    assert offline.connected is False
    assert offline.name == "tv-dhcp-name"  # nombre del lease DHCP

    bulb = devices["02:00:00:00:00:05"]
    assert bulb.name == "Lámpara salón"  # nombre personalizado (URI-encoded)
    assert bulb.connection is ConnectionType.WIFI_2_4GHZ  # columna 4 = 24G

    station_only = devices["02:00:00:00:00:06"]
    assert station_only.connected and station_only.name is None
    assert station_only.connection is ConnectionType.WIFI_2_4GHZ


def test_connected_devices(fixture_docs: dict) -> None:
    data = build_router_data(fixture_docs)
    assert len(data.connected_devices) == 5


def test_missing_optional_sections() -> None:
    docs = {
        "router_status": parse_js('var serial_number="X1";'),
    }
    data = build_router_data(docs)
    assert data.device.serial_number == "X1"
    assert data.device.model == "Livebox"
    assert data.optical is None
    assert data.wifi is None
    assert data.remote_access is None
    assert data.devices == {}
    assert data.wan.connected is None


def test_livebox_plus_detection() -> None:
    docs = {
        "router_status": parse_js(
            'var serial_number="X";\nvar hardware_model="ARLTPLUS6";\n'
            'var firmware_version="03.01.00.010";'
        )
    }
    assert build_router_data(docs).device.model == "Livebox+ 6"


def test_serial_required() -> None:
    with pytest.raises(ParseError):
        build_router_data({"router_status": JsDocument()})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1000Mbps", 1000), ("1G", 1000), ("2.5G", 2500), ("100M", 100), ("0M", None), ("", None)],
)
def test_parse_speed(raw: str, expected: int | None) -> None:
    assert parse_speed(raw) == expected


# --- Spec 004: control parental ---------------------------------------------------------


def test_access_rules(fixture_docs: dict) -> None:
    from custom_components.orange_livebox_es.api.models import AccessMode

    data = build_router_data(fixture_docs)
    assert data.access_rules is not None
    assert set(data.access_rules) == {"02:00:00:00:00:03", "02:00:00:00:00:05"}
    blocked = data.access_rule(data.devices["02:00:00:00:00:03"])
    assert blocked is not None and blocked.slot == 0 and blocked.mode is AccessMode.BLOCKED
    scheduled = data.access_rule(data.devices["02:00:00:00:00:05"])
    assert scheduled is not None and scheduled.mode is AccessMode.SCHEDULED
    assert scheduled.schedule == ["00FF00"] * 5 + ["FFFFFF"] * 2
    assert data.access_rule(data.devices["02:00:00:00:00:01"]) is None


def test_access_rules_absent_without_cgi(fixture_docs: dict) -> None:
    del fixture_docs["firewall_mac_filter"]
    assert build_router_data(fixture_docs).access_rules is None


def test_access_mac_and_device_type(fixture_docs: dict) -> None:
    devices = build_router_data(fixture_docs).devices
    laptop = devices["02:00:00:00:00:01"]
    assert laptop.access_mac == "02:00:00:00:00:01"
    # en la fila "old-name" la MAC del lease es 00:00…; gana la fila Online con lease válido
    assert devices["02:00:00:00:00:03"].access_mac == "02:00:00:00:00:03"
    assert devices["02:00:00:00:00:05"].device_type == "lightbulb"


def test_lan_ports_unknown_model_uses_all_named_ports(fixture_docs: dict) -> None:
    """Modelo no catalogado (p. ej. un Livebox 7: 3 × 1G + 1 × 2,5G): todos los puertos con
    nombre, en lugar de suponer los del Livebox 6."""
    fixture_docs["router_status"].vars["hardware_model"] = "ARLTFIBRA7"
    ports = build_router_data(fixture_docs).lan_ports
    assert [p.name for p in ports] == ["LAN1", "LAN2", "LAN3", "LAN4", "2.5G LAN"]
    assert ports[4].speed_mbps == 2500

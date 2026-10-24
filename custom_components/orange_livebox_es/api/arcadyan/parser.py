"""Conversión de los CGI Arcadyan a modelos normalizados (funciones puras)."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from ..exceptions import ParseError
from ..jsparse import JsDocument
from ..models import (
    AccessRule,
    ConnectedDevice,
    ConnectionType,
    DeviceInfo,
    LanPort,
    OpticalStatus,
    RemoteAccess,
    RouterData,
    SystemStatus,
    VoipLine,
    WanStatus,
    WifiStatus,
)

MODEL_NAMES = {
    "ARLTFIBRA6": "Livebox 6",
    "ARPLUS6": "Livebox+ 6",
}
MANUFACTURERS = {"ARLT": "Arcadyan"}

_EMPTY = {"", "null", "NULL", "--", "undefined", "N/A"}
_EMPTY_IP = _EMPTY | {"0", "0.0.0.0", "::", "0:0:0:0:0:0:0:0"}
_PLACEHOLDER_NAMES = {"name unavailable", "unknown", "--", "null"}
_MAC_RE = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")
_SPEED_RE = re.compile(r"^\s*([\d.]+)\s*([GMK]?)", re.IGNORECASE)

# Columnas de online_client (contracts/arcadyan-http.md §6)
_C_NAME, _C_IP4, _C_MAC, _C_FROM = 0, 1, 2, 4
_C_IP6_GUA, _C_IP6_LLA, _C_IP6_ULA = 5, 6, 7
_C_MODE, _C_ONLINE, _C_SSID, _C_OPT60, _C_LAST, _C_UPTIME = 8, 9, 10, 11, 12, 13
_C_IFACE, _C_LEASE_MAC, _C_CUSTOM_NAME, _C_LINK = 14, 16, 17, 18

_CONNECT_TYPES = {
    "ether": ConnectionType.ETHERNET,
    "lan": ConnectionType.ETHERNET,
    "2.4g": ConnectionType.WIFI_2_4GHZ,
    "24g": ConnectionType.WIFI_2_4GHZ,
    "5g": ConnectionType.WIFI_5GHZ,
    "5g_h": ConnectionType.WIFI_5GHZ,
    "6g": ConnectionType.WIFI_6GHZ,
}


# --- utilidades -------------------------------------------------------------------------
def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text in _EMPTY else text


def _ip(value: Any) -> str | None:
    text = _text(value)
    return None if text is None or text in _EMPTY_IP else text


def _float(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def _int(value: Any) -> int | None:
    number = _float(value)
    return None if number is None else int(number)


def _flag(value: Any) -> bool | None:
    text = _text(value)
    if text is None:
        return None
    return text in ("1", "true", "on", "up", "enable", "enabled")


def normalize_mac(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    mac = text.upper().replace("-", ":")
    if not _MAC_RE.match(mac) or mac == "00:00:00:00:00:00":
        return None
    return mac


def parse_speed(value: Any) -> int | None:
    """``1000Mbps``/``1G``/``2.5G``/``100M`` → Mb/s; ``0M`` → None."""
    text = _text(value)
    if text is None:
        return None
    match = _SPEED_RE.match(text)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2).upper()
    if unit == "G":
        number *= 1000
    elif unit == "K":
        number /= 1000
    return int(number) if number > 0 else None


def _connection_type(value: Any) -> ConnectionType:
    text = _text(value)
    if text is None:
        return ConnectionType.UNKNOWN
    return _CONNECT_TYPES.get(text.lower(), ConnectionType.UNKNOWN)


def _name(value: Any) -> str | None:
    text = _text(value)
    if text is None or text.lower() in _PLACEHOLDER_NAMES or text.lower().startswith("unknown_"):
        return None
    return text


def _doc(docs: Mapping[str, JsDocument], name: str) -> JsDocument:
    return docs.get(name) or JsDocument()


# --- secciones --------------------------------------------------------------------------
def parse_device_info(docs: Mapping[str, JsDocument]) -> DeviceInfo:
    status = _doc(docs, "router_status")
    info = _doc(docs, "info")
    serial = _text(status.var("serial_number")) or _text(status.var("gpon_sn"))
    if serial is None:
        raise ParseError("router_status no contiene serial_number")

    model_id = _text(status.var("hardware_model"))
    firmware = _text(status.var("firmware_version"))
    # La propia web distingue Livebox+ por el 2º carácter de la versión de firmware
    if firmware and len(firmware) > 1 and firmware[1] == "3":
        model_id = "ARPLUS6"
    sub_version = _text(status.var("firmware_sub_version"))
    manufacturer = _text(info.var("manufacturer")) or "ARLT"

    return DeviceInfo(
        serial_number=serial,
        model=MODEL_NAMES.get(model_id or "", f"Livebox ({model_id})" if model_id else "Livebox"),
        model_id=model_id,
        manufacturer=MANUFACTURERS.get(manufacturer, manufacturer),
        firmware_version=" ".join(p for p in (firmware, sub_version) if p) or None,
        hardware_version=_text(status.var("hardware_version")),
        bootloader_version=_text(status.var("boot_code_version")),
        mac_address=normalize_mac(info.var("wan_mac_addr")),
        isp=_text(info.var("isp")),
    )


def parse_system(docs: Mapping[str, JsDocument]) -> SystemStatus:
    status = _doc(docs, "router_status")
    system = _doc(docs, "info").var("system") or {}
    if not isinstance(system, dict):
        system = {}
    return SystemStatus(
        uptime=_int(status.var("uptime")),
        cpu_load=_float(system.get("cpuLoad")),
        memory_total_mb=_int(system.get("total_mem")),
        memory_free_mb=_int(system.get("free_mem")),
    )


def _ipv6_from_buf(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    return _ip(text.split("/")[0])


def parse_wan(docs: Mapping[str, JsDocument]) -> WanStatus:
    info = _doc(docs, "info")
    internet = _doc(docs, "infoInternet")
    lan_ip = _text(_doc(docs, "infoLan").var("lan_ip"))

    ipv4 = _ip(info.var("defroute_wan_ip")) or _ip(internet.var("defroute_wan_ip"))
    ipv6 = _ipv6_from_buf(info.var("ipv6_info_buf")) or _ipv6_from_buf(
        internet.var("ipv6_info_buf")
    )

    mode = _text(info.var("wan_mode"))
    if mode in ("ETHWAN", "AE"):
        mode = "ETH"
    four_g = info.cfg_value("4g_mode") or ""
    if "Connected" in four_g:
        mode = "4G Backup"

    # La web da la conexión por buena si hay IP; wan_link_status afina si existe
    connected: bool | None = bool(ipv4 or ipv6) if ("defroute_wan_ip" in info.vars) else None
    link = internet.var("wan_link_status")
    if isinstance(link, list):
        entries = [e for e in link if isinstance(e, list) and e]
        if entries:
            link_up = str(entries[0][0]).lower() == "up"
            connected = link_up if connected is None else (connected and link_up)

    dns = [
        server
        for server in (internet.cfg_value("wan_dns") or "").split()
        if _ip(server) and server != lan_ip
    ]
    return WanStatus(
        connected=connected,
        mode=mode,
        ipv4=ipv4,
        ipv6=ipv6,
        dns_servers=dns,
        uptime=_int(internet.var("wan_connTime")),
    )


def parse_optical(docs: Mapping[str, JsDocument]) -> OpticalStatus | None:
    ftth = docs.get("infoFtth")
    if ftth is None:
        return None
    status = ftth.var("traciver_status") or {}
    counters = ftth.var("traffic_counter") or {}
    if not isinstance(status, dict) or not status:
        return None
    if not isinstance(counters, dict):
        counters = {}
    return OpticalStatus(
        link_up=_flag(status.get("phy_link")),
        rx_power=_float(status.get("rx_power")),
        tx_power=_float(status.get("tx_power")),
        temperature=_float(status.get("temp")),
        voltage=_float(status.get("volt")),
        bias_current=_float(status.get("bias")),
        unicast_rx_frames=_int(counters.get("unicastreceiveframes")),
        unicast_tx_frames=_int(counters.get("unicasttransmitframes")),
        multicast_rx_frames=_int(counters.get("multicastacceptframes")),
        multicast_drop_frames=_int(counters.get("multicastdropframes")),
    )


#: puertos que muestra la web (``support_information_lan.htm``: lan1…lan4). El firmware
#: declara además «2.5G LAN» (LogName4) y un 6.º puerto que el Livebox 6 español no tiene.
WEB_VISIBLE_LAN_PORTS = 4


def parse_lan_ports(docs: Mapping[str, JsDocument]) -> list[LanPort]:
    lan = _doc(docs, "infoLan")
    rows = lan.var("lan_status_list") or []
    ports: list[LanPort] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        index = _int(row[0])
        if index is None or not 1 <= index <= WEB_VISIBLE_LAN_PORTS:
            continue
        name = lan.cfg_value(f"LogName{index - 1}") or f"LAN{index}"
        ports.append(
            LanPort(
                index=index,
                name=name,
                link_up=str(row[1]).lower() == "up",
                speed_mbps=parse_speed(row[2]) if len(row) > 2 else None,
                full_duplex=(str(row[3]).upper() == "FD") if len(row) > 3 else None,
            )
        )
    return ports


def parse_wifi(docs: Mapping[str, JsDocument]) -> WifiStatus | None:
    combine = docs.get("wlan_combine")
    guest = docs.get("wlan_guest")
    if combine is None and guest is None:
        return None
    combine = combine or JsDocument()
    guest = guest or JsDocument()

    guest_flags = [_flag(guest.cfg_value(name)) for name in ("ssid_enable24G3", "ssid_enable5G3")]
    guest_known = [f for f in guest_flags if f is not None]
    return WifiStatus(
        enabled_24g=_flag(combine.cfg_value("wl_enable24G")),
        enabled_5g=_flag(combine.cfg_value("wl_enable5G")),
        ssid_24g=_text(combine.cfg_value("wl_ssid24G")),
        ssid_5g=_text(combine.cfg_value("wl_ssid5G")),
        channel_24g=_int(combine.var("curr_channel_24g")),
        channel_5g=_int(combine.var("curr_channel_5g")),
        schedule_enabled=_flag(combine.cfg_value("wifi_schedule_enable")),
        guest_enabled=any(guest_known) if guest_known else None,
        guest_ssid=_text(guest.cfg_value("wl_ssid24G3")) or _text(combine.cfg_value("wl_ssid24G3")),
    )


def parse_voip(docs: Mapping[str, JsDocument]) -> list[VoipLine]:
    raw = _text(_doc(docs, "network_connected").var("szSIP_Register_Status"))
    if raw is None:
        raw = _text(_doc(docs, "phones").var("szSIP_Line_Register_Status"))
    lines: list[VoipLine] = []
    for chunk in (raw or "").split("|"):
        parts = chunk.split()
        if len(parts) >= 2 and parts[0] not in _EMPTY:
            lines.append(VoipLine(number=parts[0], registered=parts[1] == "1"))
    return lines


def parse_remote_access(docs: Mapping[str, JsDocument]) -> RemoteAccess | None:
    remote = docs.get("remote_management_osp")
    if remote is None or "rm_en" not in remote.cfg:
        return None
    return RemoteAccess(
        enabled=_flag(remote.cfg_value("rm_en")) is True,
        port=_int(remote.cfg_value("rm_port")),
    )


def parse_firewall_level(docs: Mapping[str, JsDocument]) -> str | None:
    firewall = docs.get("firewall_main")
    if firewall is None:
        return None
    if _flag(firewall.cfg_value("firewall_enable")) is False:
        return "disabled"
    return {"0": "low", "1": "medium", "2": "high", "3": "custom"}.get(
        firewall.cfg_value("firewall_level") or ""
    )


def _station_index(stations: Any) -> dict[str, dict[str, Any]]:
    """Estaciones por MAC; si hay duplicadas gana la que está online."""
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(stations, list):
        return index
    for station in stations:
        if not isinstance(station, dict):
            continue
        mac = normalize_mac(station.get("station_mac"))
        if mac is None:
            continue
        current = index.get(mac)
        if current is None or (
            str(station.get("online")) == "1" and str(current.get("online")) != "1"
        ):
            index[mac] = station
    return index


def _custom_types(clients: JsDocument) -> dict[str, str]:
    types: dict[str, str] = {}
    for key, entry in clients.cfg.items():
        if not key.startswith("client_mac"):
            continue
        mac = normalize_mac(entry.value)
        device_type = _text(clients.cfg_value("client_deviceType" + key[len("client_mac") :]))
        if mac and device_type:
            types[mac] = device_type
    return types


def _custom_names(clients: JsDocument) -> dict[str, str]:
    names: dict[str, str] = {}
    for key, entry in clients.cfg.items():
        if not key.startswith("client_mac"):
            continue
        mac = normalize_mac(entry.value)
        name = _name(clients.cfg_value("client_hostname" + key[len("client_mac") :]))
        if mac and name:
            names[mac] = name
    return names


def parse_devices(docs: Mapping[str, JsDocument]) -> dict[str, ConnectedDevice]:
    clients = _doc(docs, "clients")
    station_info = clients.var("station_info") or {}
    stations = _station_index(
        station_info.get("stations") if isinstance(station_info, dict) else None
    )
    custom = _custom_names(clients)
    custom_types = _custom_types(clients)

    dhcp_names: dict[str, str] = {}
    dhcp = clients.var("dhcp_client") or []
    if isinstance(dhcp, list):
        for i in range(0, len(dhcp) - 2, 5):
            mac = normalize_mac(dhcp[i + 2])
            name = _name(dhcp[i])
            if mac and name:
                dhcp_names.setdefault(mac, name)

    # Fusión de filas duplicadas por MAC: gana Online, luego la más reciente
    rows: dict[str, list[Any]] = {}
    for row in clients.var("online_client") or []:
        if not isinstance(row, list) or len(row) <= _C_UPTIME:
            continue
        mac = normalize_mac(row[_C_MAC])
        if mac is None:
            continue
        current = rows.get(mac)
        if current is None:
            rows[mac] = row
            continue
        row_online = row[_C_ONLINE] == "Online"
        cur_online = current[_C_ONLINE] == "Online"
        if (row_online and not cur_online) or (
            row_online == cur_online and str(row[_C_LAST]) > str(current[_C_LAST])
        ):
            rows[mac] = row

    devices: dict[str, ConnectedDevice] = {}
    for mac, row in rows.items():
        station = stations.get(mac, {})
        connected = row[_C_ONLINE] == "Online"
        connection = (
            _connection_type(station.get("connect_type")) if station else (ConnectionType.UNKNOWN)
        )
        if connection is ConnectionType.UNKNOWN:
            connection = _connection_type(row[_C_FROM])

        signal = _int(station.get("signal_strength")) if connection.is_wifi else None
        link_rate = parse_speed(station.get("link_rate"))
        if link_rate is None and connection is ConnectionType.ETHERNET and len(row) > _C_LINK:
            link_rate = parse_speed(row[_C_LINK])
        ssid = _text(station.get("connect_ssid")) or _text(row[_C_SSID])

        hostname = _name(row[_C_NAME])
        name = (
            custom.get(mac)
            or (_name(row[_C_CUSTOM_NAME]) if len(row) > _C_CUSTOM_NAME else None)
            or hostname
            or _name(station.get("station_name"))
            or dhcp_names.get(mac)
        )
        lease_mac = normalize_mac(row[_C_LEASE_MAC]) if len(row) > _C_LEASE_MAC else None
        access_mac = lease_mac or mac
        devices[mac] = ConnectedDevice(
            mac=mac,
            connected=connected,
            name=name,
            hostname=hostname or dhcp_names.get(mac),
            ip=_ip(row[_C_IP4]) or _ip(station.get("station_ip")),
            ipv6=_ip(row[_C_IP6_GUA]) or _ip(row[_C_IP6_ULA]),
            connection=connection,
            ssid=ssid if connection.is_wifi else None,
            signal_strength=signal if signal else None,
            link_rate_mbps=link_rate,
            interface=_text(row[_C_IFACE]) if len(row) > _C_IFACE else None,
            address_source=_text(row[_C_MODE]),
            vendor_class=_text(row[_C_OPT60]),
            last_seen=_text(row[_C_LAST]),
            connected_time=_int(row[_C_UPTIME]),
            access_mac=access_mac,
            device_type=custom_types.get(access_mac) or custom_types.get(mac),
        )

    # Estaciones online que no aparezcan en online_client
    for mac, station in stations.items():
        if mac in devices or str(station.get("online")) != "1":
            continue
        connection = _connection_type(station.get("connect_type"))
        devices[mac] = ConnectedDevice(
            mac=mac,
            connected=True,
            name=custom.get(mac) or _name(station.get("station_name")) or dhcp_names.get(mac),
            hostname=_name(station.get("station_name")),
            ip=_ip(station.get("station_ip")),
            connection=connection,
            ssid=_text(station.get("connect_ssid")) if connection.is_wifi else None,
            signal_strength=(_int(station.get("signal_strength")) or None)
            if connection.is_wifi
            else None,
            link_rate_mbps=parse_speed(station.get("link_rate")),
        )
    return devices


def parse_access_rules(docs: Mapping[str, JsDocument]) -> dict[str, AccessRule] | None:
    """Reglas del control parental (filtro MAC, spec 004). ``None`` si no hay CGI."""
    mac_filter = docs.get("firewall_mac_filter")
    if mac_filter is None or not any(k.startswith("macFilter_mac_") for k in mac_filter.cfg):
        return None
    rules: dict[str, AccessRule] = {}
    for slot in mac_filter_slots(mac_filter):
        mac = normalize_mac(mac_filter.cfg_value(f"macFilter_mac_{slot}"))
        if mac is None or _flag(mac_filter.cfg_value(f"macFilter_enable_{slot}")) is not True:
            continue
        schedule = [
            (mac_filter.cfg_value(f"macFilter_sch_{slot}_{day}") or "000000").upper()
            for day in range(mac_filter_days(mac_filter))
        ]
        rules[mac] = AccessRule(slot=slot, mac=mac, schedule=schedule)
    return rules


def mac_filter_slots(doc: JsDocument) -> list[int]:
    """Huecos del filtro MAC declarados por el router (16 en el Livebox 6)."""
    return sorted(
        int(key.removeprefix("macFilter_mac_"))
        for key in doc.cfg
        if key.startswith("macFilter_mac_") and key.removeprefix("macFilter_mac_").isdigit()
    )


def mac_filter_days(doc: JsDocument) -> int:
    """Días por horario (7: lunes … domingo)."""
    return sum(1 for key in doc.cfg if key.startswith("macFilter_sch_0_")) or 7


def raw_snapshot(docs: Mapping[str, JsDocument]) -> dict[str, Any]:
    """Volcado de los CGI para diagnósticos (se redacta en la capa HA)."""
    return {
        name: {
            "vars": doc.vars,
            "cfg": {key: entry.value for key, entry in doc.cfg.items() if entry.raw_value},
        }
        for name, doc in docs.items()
    }


def build_router_data(docs: Mapping[str, JsDocument]) -> RouterData:
    """Construye ``RouterData`` a partir de los CGI parseados."""
    return RouterData(
        device=parse_device_info(docs),
        system=parse_system(docs),
        wan=parse_wan(docs),
        optical=parse_optical(docs),
        lan_ports=parse_lan_ports(docs),
        wifi=parse_wifi(docs),
        voip_lines=parse_voip(docs),
        remote_access=parse_remote_access(docs),
        firewall_level=parse_firewall_level(docs),
        devices=parse_devices(docs),
        access_rules=parse_access_rules(docs),
        raw=raw_snapshot(docs),
    )

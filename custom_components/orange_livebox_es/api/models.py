"""Modelos normalizados, independientes del firmware (ver specs/001/data-model.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ConnectionType(StrEnum):
    """Tipo de enlace de un cliente."""

    ETHERNET = "ethernet"
    WIFI_2_4GHZ = "wifi_2_4ghz"
    WIFI_5GHZ = "wifi_5ghz"
    WIFI_6GHZ = "wifi_6ghz"
    UNKNOWN = "unknown"

    @property
    def is_wifi(self) -> bool:
        return self in (
            ConnectionType.WIFI_2_4GHZ,
            ConnectionType.WIFI_5GHZ,
            ConnectionType.WIFI_6GHZ,
        )


@dataclass(slots=True)
class DeviceInfo:
    serial_number: str
    model: str
    manufacturer: str
    model_id: str | None = None
    firmware_version: str | None = None
    hardware_version: str | None = None
    bootloader_version: str | None = None
    mac_address: str | None = None
    isp: str | None = None


@dataclass(slots=True)
class SystemStatus:
    uptime: int | None = None
    cpu_load: float | None = None
    memory_total_mb: int | None = None
    memory_free_mb: int | None = None

    @property
    def memory_usage(self) -> float | None:
        if not self.memory_total_mb or self.memory_free_mb is None:
            return None
        used = self.memory_total_mb - self.memory_free_mb
        return round(used * 100 / self.memory_total_mb, 1)


@dataclass(slots=True)
class WanStatus:
    connected: bool | None = None
    mode: str | None = None
    ipv4: str | None = None
    ipv6: str | None = None
    dns_servers: list[str] = field(default_factory=list)
    uptime: int | None = None


@dataclass(slots=True)
class OpticalStatus:
    link_up: bool | None = None
    rx_power: float | None = None
    tx_power: float | None = None
    temperature: float | None = None
    voltage: float | None = None
    bias_current: float | None = None
    unicast_rx_frames: int | None = None
    unicast_tx_frames: int | None = None
    multicast_rx_frames: int | None = None
    multicast_drop_frames: int | None = None


@dataclass(slots=True)
class LanPort:
    index: int
    name: str
    link_up: bool
    speed_mbps: int | None = None
    full_duplex: bool | None = None


@dataclass(slots=True)
class WifiStatus:
    enabled_24g: bool | None = None
    enabled_5g: bool | None = None
    ssid_24g: str | None = None
    ssid_5g: str | None = None
    channel_24g: int | None = None
    channel_5g: int | None = None
    schedule_enabled: bool | None = None
    guest_enabled: bool | None = None
    guest_ssid: str | None = None

    @property
    def enabled(self) -> bool | None:
        """La web considera la WiFi activa solo si lo están ambas bandas."""
        if self.enabled_24g is None and self.enabled_5g is None:
            return None
        return bool(self.enabled_24g) and bool(self.enabled_5g)


@dataclass(slots=True)
class VoipLine:
    number: str
    registered: bool


@dataclass(slots=True)
class RemoteAccess:
    enabled: bool
    port: int | None = None


class AccessMode(StrEnum):
    """Modo de acceso a Internet de un cliente (control parental, spec 004)."""

    ALLOWED = "allowed"
    BLOCKED = "blocked"
    SCHEDULED = "scheduled"


@dataclass(slots=True)
class AccessRule:
    """Regla del filtro MAC del router: un horario semanal (lunes … domingo)."""

    slot: int
    mac: str
    schedule: list[str]

    @property
    def mode(self) -> AccessMode:
        days = [(day or "000000").upper() for day in self.schedule]
        if all(day == "000000" for day in days):
            return AccessMode.BLOCKED
        if all(day == "FFFFFF" for day in days):
            return AccessMode.ALLOWED
        return AccessMode.SCHEDULED


@dataclass(slots=True)
class ConnectedDevice:
    mac: str
    connected: bool
    name: str | None = None
    hostname: str | None = None
    ip: str | None = None
    ipv6: str | None = None
    connection: ConnectionType = ConnectionType.UNKNOWN
    ssid: str | None = None
    signal_strength: int | None = None
    link_rate_mbps: int | None = None
    interface: str | None = None
    address_source: str | None = None
    vendor_class: str | None = None
    last_seen: str | None = None
    connected_time: int | None = None
    #: MAC con la que la web identifica al cliente en filtros/nombres (la del lease DHCP)
    access_mac: str | None = None
    device_type: str | None = None


@dataclass(slots=True)
class RouterData:
    device: DeviceInfo
    system: SystemStatus = field(default_factory=SystemStatus)
    wan: WanStatus = field(default_factory=WanStatus)
    optical: OpticalStatus | None = None
    lan_ports: list[LanPort] = field(default_factory=list)
    wifi: WifiStatus | None = None
    voip_lines: list[VoipLine] = field(default_factory=list)
    remote_access: RemoteAccess | None = None
    firewall_level: str | None = None
    devices: dict[str, ConnectedDevice] = field(default_factory=dict)
    #: reglas de acceso por MAC (``None`` si el router no expone el filtro)
    access_rules: dict[str, AccessRule] | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def connected_devices(self) -> list[ConnectedDevice]:
        return [d for d in self.devices.values() if d.connected]

    def access_rule(self, device: ConnectedDevice) -> AccessRule | None:
        if not self.access_rules:
            return None
        return self.access_rules.get(device.access_mac or device.mac) or self.access_rules.get(
            device.mac
        )

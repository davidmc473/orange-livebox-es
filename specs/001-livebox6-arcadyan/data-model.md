# Modelo de datos 001

Modelos normalizados de `api/models.py`. Son independientes del firmware: cualquier driver
futuro debe producir un `RouterData`. Un campo `None` significa «no disponible en este
modelo» y la entidad correspondiente no se crea (o queda sin valor).

```text
RouterData
├── device: DeviceInfo
│   ├── serial_number: str            ← router_status.serial_number   (unique_id)
│   ├── model: str                    ← "Livebox 6"
│   ├── model_id: str | None          ← router_status.hardware_model  ("ARLTFIBRA6")
│   ├── manufacturer: str             ← "Arcadyan" (info.manufacturer = "ARLT")
│   ├── firmware_version: str | None  ← firmware_version + " " + firmware_sub_version
│   ├── hardware_version: str | None
│   ├── bootloader_version: str | None
│   ├── mac_address: str | None       ← info.wan_mac_addr (normalizada a MAYÚSCULAS)
│   └── isp: str | None
├── system: SystemStatus
│   ├── uptime: int | None            (s)
│   ├── cpu_load: float | None        (%)
│   └── memory_total_mb / memory_free_mb: int | None → memory_usage (%) calculado
├── wan: WanStatus
│   ├── connected: bool | None        ← infoInternet.wan_link_status[0][0] == "up"
│   ├── mode: str | None              ← "GPON" / "ETH" (ETHWAN/AE → ETH, como la web)
│   ├── ipv4 / ipv6: str | None       (ipv6 None si vacío o "::")
│   ├── dns_servers: list[str]
│   └── uptime: int | None            ← wan_connTime (s)
├── optical: OpticalStatus | None
│   ├── link_up: bool | None
│   ├── rx_power / tx_power: float | None (dBm)
│   ├── temperature (°C) / voltage (V) / bias_current (mA): float | None
│   └── unicast_rx_frames / unicast_tx_frames / multicast_rx_frames / multicast_drop_frames: int | None
├── lan_ports: list[LanPort]
│   └── LanPort(index:int, name:str, link_up:bool, speed_mbps:int|None, full_duplex:bool|None)
├── wifi: WifiStatus | None
│   ├── enabled_24g / enabled_5g: bool | None
│   ├── ssid_24g / ssid_5g: str | None
│   ├── channel_24g / channel_5g: int | None
│   ├── schedule_enabled: bool | None
│   ├── guest_enabled: bool | None    (alguna banda del SSID índice 3 activa)
│   └── guest_ssid: str | None
├── voip_lines: list[VoipLine]
│   └── VoipLine(number:str, registered:bool)
├── remote_access: RemoteAccess | None
│   └── RemoteAccess(enabled:bool, port:int|None)
├── firewall_level: str | None
├── devices: dict[str, ConnectedDevice]     (clave = MAC en MAYÚSCULAS)
│   └── ConnectedDevice
│       ├── mac: str
│       ├── name: str | None          prioridad: nombre personalizado > col.17 > hostname > station_name > lease DHCP
│       ├── hostname: str | None
│       ├── ip: str | None
│       ├── ipv6: str | None
│       ├── connected: bool
│       ├── connection: ConnectionType  (ethernet | wifi_2_4ghz | wifi_5ghz | wifi_6ghz | unknown)
│       ├── ssid: str | None
│       ├── signal_strength: int | None  (dBm, solo WiFi)
│       ├── link_rate_mbps: int | None
│       ├── interface: str | None
│       ├── address_source: str | None   (DHCP / Static)
│       ├── vendor_class: str | None
│       ├── last_seen: str | None        (texto del router)
│       └── connected_time: int | None   (s)
└── raw: dict[str, dict]                 CGI parseados (solo para diagnósticos; se redactan)
```

## Reglas de normalización

| Regla | Detalle |
|-------|---------|
| MAC | Siempre `AA:BB:CC:DD:EE:FF`. |
| Fusión de clientes | Por MAC; gana `Online`; empate → `last_conn_time` más reciente. |
| `connection` | De `station_info.connect_type`: `Ether`→ethernet, `24G`→wifi_2_4ghz, `5G`/`5G_H`→wifi_5ghz, `6G`→wifi_6ghz; si no hay estación, `online_client[4]` (`LAN`→ethernet). |
| Velocidades | `"1000Mbps"`→1000, `"1G"`→1000, `"2.5G"`→2500, `"100M"`→100, `"0M"`→`None`. |
| Números «vacíos» | `"0"`, `""`, `"NULL"`, `"--"` → `None` en campos de texto opcionales. |
| Nombres placeholder | `"name unavailable"`, `"unknown_<mac>"`, `"--"` se ignoran. |

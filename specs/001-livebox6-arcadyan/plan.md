# Plan técnico 001 — Livebox 6 (Arcadyan)

Entrada: [`spec.md`](spec.md) · Protocolo: [`contracts/arcadyan-http.md`](contracts/arcadyan-http.md)
· Modelos: [`data-model.md`](data-model.md) · Hallazgos: [`research.md`](research.md)

## 1. Stack

| Aspecto | Decisión |
|---------|----------|
| Lenguaje | Python ≥ 3.13 (el de Home Assistant) |
| HTTP | `aiohttp` (sesión propia con `DummyCookieJar`; cookie `SID` gestionada a mano) |
| Cripto | `cryptography` (AES-256-CBC) + `hashlib` (MD5) |
| HA mínimo | 2024.12 (`entry.runtime_data`, `ConfigFlowResult`) |
| Tests | `pytest`, `pytest-asyncio`, `aiohttp` test server; `pytest-homeassistant-custom-component` para el flujo de configuración |
| Distribución | HACS (repositorio tipo *integration*) |

## 2. Arquitectura

```
custom_components/orange_livebox_es/
├── api/                      ← SIN dependencias de Home Assistant (constitución IV)
│   ├── __init__.py           exports + async_create_client() (detección de driver)
│   ├── base.py               LiveboxClient (ABC) + Feature
│   ├── models.py             dataclasses normalizadas (RouterData, ConnectedDevice…)
│   ├── exceptions.py         LiveboxError, CannotConnect, InvalidAuth, LoginLocked, UnsupportedRouter
│   ├── jsparse.py            parser de literales JS + addCfg
│   ├── crypto.py             material de página, do_encode/do_decode, campos de login
│   ├── redact.py             lista de claves sensibles y utilidades de redacción
│   └── arcadyan/
│       ├── __init__.py
│       ├── client.py         ArcadyanLiveboxClient (login, sesión, CGI, escrituras)
│       └── parser.py         CGI → RouterData (funciones puras, testeables)
├── __init__.py               setup/unload de la entrada, runtime_data
├── config_flow.py            user + reauth + options
├── coordinator.py            LiveboxDataUpdateCoordinator
├── entity.py                 LiveboxEntity (device_info común)
├── sensor.py / binary_sensor.py / switch.py / button.py / device_tracker.py
├── diagnostics.py
├── const.py · manifest.json · strings.json · translations/{en,es}.json · icons.json
```

### Flujo de un ciclo de sondeo

```
coordinator._async_update_data()
  └─ client.async_get_data()
       ├─ _ensure_session()            login si no hay SID
       ├─ GET support_leds.htm         → clave/IV/token (si 302→login: relogin 1 vez)
       ├─ GET cgi_<n>.js × 11          secuencial, Referer = página anterior
       └─ parser.build_router_data()   → RouterData
```

### Escritura

```
client.async_set_guest_wifi(True)
  ├─ GET wifi_guest.htm               → material de esa página
  ├─ GET cgi_wlan_guest.js            → ids y valores actuales
  ├─ POST apply_abstract.cgi          action=ui_wireless + cfg cambiados
  └─ coordinator.async_request_refresh()
```

## 3. Catálogo de entidades

`key` = sufijo del `unique_id` (`<serie>_<key>`). *Diag* = `EntityCategory.DIAGNOSTIC`.
*Off* = deshabilitada por defecto (**anulado por la spec 002: todas habilitadas**).

### Sensores

| key | Nombre (es) | Unidad / clase | Notas |
|-----|-------------|----------------|-------|
| `wan_ipv4` | IP pública | — | |
| `wan_ipv6` | IPv6 WAN | — | Off |
| `wan_mode` | Modo WAN | — | Diag |
| `dns_servers` | Servidores DNS | — | Diag, Off |
| `wan_connected_since` | Conectado desde | `timestamp` | |
| `last_boot` | Último arranque | `timestamp` | Diag |
| `cpu_load` | Carga de CPU | % · measurement | Diag |
| `memory_usage` | Uso de memoria | % · measurement | Diag |
| `connected_devices` | Dispositivos conectados | measurement | atributos: por cable / wifi |
| `wifi_devices` | Dispositivos WiFi | measurement | |
| `ethernet_devices` | Dispositivos por cable | measurement | Off |
| `optical_rx_power` | Potencia óptica RX | dBm · `signal_strength` | Diag |
| `optical_tx_power` | Potencia óptica TX | dBm · `signal_strength` | Diag |
| `optical_temperature` | Temperatura del transceptor | °C · `temperature` | Diag |
| `optical_voltage` | Tensión del transceptor | V · `voltage` | Diag, Off |
| `optical_bias_current` | Corriente de polarización | mA · `current` | Diag, Off |
| `unicast_rx_frames` | Tramas unicast recibidas | total_increasing | Diag, Off |
| `unicast_tx_frames` | Tramas unicast enviadas | total_increasing | Diag, Off |
| `wifi_channel_24g` | Canal WiFi 2.4 GHz | — | Diag |
| `wifi_channel_5g` | Canal WiFi 5 GHz | — | Diag |
| `wifi_ssid` | SSID WiFi | — | Diag |
| `guest_wifi_ssid` | SSID invitados | — | Diag, Off |
| `firewall_level` | Nivel de firewall | — | Diag, Off |

### Binary sensors

| key | Nombre | Clase | Notas |
|-----|--------|-------|-------|
| `internet` | Internet | connectivity | |
| `optical_link` | Enlace óptico | connectivity | Diag |
| `voip_line` | Línea telefónica | connectivity | atributo `number` (enmascarado salvo últimas 3 cifras) |
| `lan_port_<n>` | Puerto LAN1…LAN4 | connectivity | Diag, Off; atributos `speed`, `duplex` |

### Switches

| key | Nombre | Notas |
|-----|--------|-------|
| `wifi` | WiFi | on si ambas bandas activas |
| `guest_wifi` | WiFi de invitados | on si alguna banda del SSID 3 activa |
| `remote_access` | Acceso remoto | spec 002; atributo `port` |

### Botones

| key | Nombre | Clase |
|-----|--------|-------|
| `reboot` | Reiniciar | `restart` |

### Device tracker

Una `ScannerEntity` por MAC (`unique_id = mac`), creada dinámicamente con un *listener* del
coordinador. `mac_address`, `ip_address`, `hostname` se exponen para que HA enlace con
otros dispositivos que compartan MAC.

## 4. Manejo de errores

| Situación | API | Coordinador / HA |
|-----------|-----|------------------|
| Timeout / conexión | `CannotConnect` | `UpdateFailed` → entidades no disponibles |
| 302 a `login.htm` en mitad de ciclo | relogin 1 vez y reintento | transparente |
| Credenciales rechazadas | `InvalidAuth` | `ConfigEntryAuthFailed` → reauth |
| Bloqueo (`remaining_time>0`) | `LoginLocked(seconds)` | `UpdateFailed` (no reauth) |
| Escritura falla | `LiveboxError` | `HomeAssistantError` traducido |

## 5. Testing

| Nivel | Qué | Cómo |
|-------|-----|------|
| Unit | `jsparse`, `crypto`, `parser` | fixtures sintéticas en `tests/fixtures/arcadyan/` |
| Protocolo | login, relogin, Referer, lockout, escrituras | servidor `aiohttp` falso que valida cifrado y cabeceras (`tests/fake_router.py`) |
| HA | config flow (ok, auth, lock, conexión, duplicado), setup de plataformas | `pytest-homeassistant-custom-component` |
| En vivo | sondeo real, solo lectura por defecto | `scripts/live_probe.py` con `LIVEBOX_PASSWORD` |

## 6. Extensión a otros routers

1. Capturar `login.htm` + CGI del modelo nuevo → fixtures.
2. Si es Arcadyan con otra web: subclase/ajustes en `api/arcadyan/` (lista de CGI, mapeo).
3. Si es otra familia (p. ej. Sagemcom `sysbus`): nuevo paquete `api/<driver>/` que
   implemente `LiveboxClient` y registrarlo en `api/__init__.py::DRIVERS`.
4. Las entidades se crean según `client.features` y los campos `None` de `RouterData`.

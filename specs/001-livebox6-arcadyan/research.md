# Research 001 — Hallazgos sobre el Livebox 6 (Arcadyan) y decisiones

Sesión de exploración: 2026-10-24, router en `192.168.1.1`.

## Identificación del equipo

| Dato | Valor observado |
|------|-----------------|
| Cabecera `Server` | `Arcadyan httpd 1.0` |
| `hardware_model` | `ARLTFIBRA6` |
| `hardware_version` | `ARLTLBFIB61.0.0` |
| `firmware_version` | `02.03.01.035D` (`build204`) — la web lo muestra como `ARFIBRA6-sp-…` (si el 2º carácter es `3` → `ARPLUS6-sp-…`, Livebox+) |
| `boot_code_version` | `SAHBL_20.99.14` |
| `manufacturer` | `ARLT` (Arcadyan) · `isp`: `Orange` |
| WAN | `GPON` (ONT integrada), `wan_type=5` |
| Puertos | LAN1–LAN4 (1G). El firmware declara además «2.5G LAN» y un 6.º puerto que **este modelo no tiene** (la web solo muestra LAN1–LAN4; corregido tras aviso del usuario) |

## Hallazgos clave

1. **Cifrado de formularios**: AES-256-CBC estándar (S-box estándar, CBC estándar, padding
   con ceros). Verificado con `cryptography` haciendo login real. → *Decisión*: usar
   `cryptography` (ya en HA) en vez de portar el AES en JS.
2. **MD5** de `arc-crypt.js` es MD5 estándar (tabla `sin`), verificado con el login.
3. **Referer obligatorio** en los CGI (sin él → 404, lo que despista: no es 401/302).
4. **Token reutilizable** dentro de la sesión para múltiples CGI; se obtiene de cualquier
   página autenticada. → *Decisión*: 1 página ligera + N CGI por ciclo.
5. ~~**Sesiones concurrentes** permitidas~~ → **corregido en la spec 003**: el router solo admite
   una sesión activa; con el mismo User-Agent parecían convivir (de ahí la conclusión errónea).
6. **Bloqueo**: 3 contraseñas erróneas → 60 s de bloqueo (`remaining_time`). → *Decisión*:
   no reintentar login tras fallo de credenciales; levantar reauth.
7. **Clientes**: `online_client` incluye histórico (Online/Offline) con MAC duplicadas
   (p. ej. reserva estática + lease dinámico). `station_info` aporta el tipo real de
   enlace (Ether/24G/5G), RSSI y velocidad; `online_client[4]` siempre dice `LAN`.
8. **Óptica**: `infoFtth` da RX ≈ −18 dBm, TX ≈ 2.4 dBm, temperatura, tensión y bias:
   muy útil para diagnosticar la fibra.
9. **Datos sensibles presentes en los CGI**: claves WiFi (`sharedkey*`), PIN WPS
   (`gnWpsDevPIN`), contraseña del ONT (`ont_pwd`, hex), usuario/contraseña de acceso
   remoto (`remote_user`/`remote_pwd`), número de teléfono. → Lista de redacción.
10. **Acceso remoto** (`rm_en`, `rm_port`): puede estar activo sin que el usuario lo sepa; se expone
    como `binary_sensor` de problema para alertar al usuario.

## Tamaños medidos (un ciclo)

| Recurso | Bytes |
|---------|-------|
| página token (`support_leds.htm`) | ~11.5 K |
| `clients` | ~87 K |
| `wlan_combine` | ~41 K |
| `infoInternet` + `infoLan` + `infoFtth` + `info` + `router_status` | ~10 K |
| `wlan_guest` + `network_connected` + `remote_management_osp` + `firewall_main` | ~37 K |
| **Total** | **≈ 190 K** (cumple NFR-002) |

## Alternativas descartadas

| Alternativa | Motivo del descarte |
|-------------|---------------------|
| Ejecutar el JS con un motor (py_mini_racer, etc.) | Dependencia nativa pesada, no disponible en HA OS para todas las arquitecturas. |
| Scraping del HTML renderizado | Los datos están en los CGI JS; el HTML es solo plantilla. |
| Integración `livebox` existente | Usa `sysbus` (Sagemcom); este firmware no lo implementa. |
| Cookie jar de `aiohttp` | No guarda cookies para hosts IP salvo `unsafe=True`; se gestiona `SID` manualmente. |

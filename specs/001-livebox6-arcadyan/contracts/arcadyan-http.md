# Contrato: protocolo HTTP de la web Arcadyan (Livebox 6 Orange ES)

Obtenido por ingeniería inversa de `login.htm`, `js/global.js`, `js/arc-crypt.js` y
`js/subformvar.js` del firmware `02.03.01.035D build204`. Servidor: `Arcadyan httpd 1.0`.

## 1. Material criptográfico por página

Cada página HTML autenticada (y `login.htm`) termina con una imagen espaciadora:

```html
<img title=spacer src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7<B64>" border=0>
```

La función ofuscada `ArcBase._t` (variable `enkripsi` de `global.js`: base64 → XOR 3 →
`unescape`) toma `src.substr(78)`, lo decodifica en base64 y lo trocea:

| Llamada        | Trozo                  | Uso                       |
|----------------|------------------------|---------------------------|
| `_t(2)`        | `[0:32]`               | Clave AES-256             |
| `_t(3)`        | `[32:48]`              | IV AES-CBC                |
| `_t()`/`_t(1)` | `[48:]`                | Token `httoken` / `_tn`   |

> Los 78 caracteres saltados son `data:image/gif;base64,` (22) + el GIF 1×1 (56).

## 2. `do_encode(s)`

AES-256-CBC estándar con clave/IV anteriores, *padding* con ceros hasta múltiplo de 16
(sin bloque extra si ya es múltiplo) y salida como `%xx%xx…` (hex en minúsculas con `%`).
Cadena vacía → se devuelve vacía sin cifrar. Cada llamada reinicia el IV.

## 3. Login

1. `GET /login.htm` → extraer clave/IV/token. Si `var remaining_time=parseInt('N')` con
   `N > 0` → router bloqueado N segundos (3 fallos seguidos).
2. `POST /login.cgi` (`application/x-www-form-urlencoded`):

| Campo      | Valor |
|------------|-------|
| `httoken`  | token de `login.htm` |
| `dfr597hf` | `do_encode(btoa(rand32 + " " + md5hex(btoa(usuario))))` |
| `cnlvd2xh` | `do_encode(btoa(rand32 + " " + md5hex(btoa(contraseña))))` |

`rand32` = 32 caracteres aleatorios de `[0-9a-z]`.

3. Respuesta:
   - `302 Location: /index.htm` + `Set-Cookie: SID=<64 dígitos>; PATH=/; HttpOnly` → OK.
   - `302 Location: /login.htm?err=1` → credenciales no válidas.
   - `err=3` → sesión caducada.

Desde la LAN el usuario está fijado a `admin` en la web. Se admiten **sesiones
concurrentes** (verificado). Inactividad: `szLoginTimeout = 10` min.

## 4. Lectura de datos (CGI)

```
GET /cgi/cgi_<nombre>.js?_tn=<token>&_t=<epoch_ms>&_=<epoch_ms>
Cookie: SID=…
Referer: http://<host>/<página que proporcionó el token>
```

- **Sin `Referer` → 404.** Sin sesión → `302 /login.htm`.
- Un mismo token sirve para varios CGI.
- Respuesta: JavaScript con sentencias de nivel superior:
  - `var nombre=<literal JS>;` (cadenas con `'` o `"`, arrays, objetos con claves sin
    comillas o con comillas simples, números, `null`).
  - `addCfg("nombre", "<id numérico>", "<valor>"[, cifrado]);` → el `id` es el que se usa
    para escribir. Los valores pueden ir *URI-encoded* (`getCfg` aplica
    `decodeURIComponent`).
  - Reasignaciones sin `var` (p. ej. `traciver_status={…}` en `infoFtth`).

### CGI utilizados

| CGI | Página que lo usa | Datos |
|-----|-------------------|-------|
| `router_status` | support_information | `hardware_model`, `firmware_version`, `firmware_sub_version`, `boot_code_version`, `hardware_version`, `serial_number`, `gpon_sn`, `uptime` (s, decimal) |
| `info` | support_information | `manufacturer`, `isp`, `wan_mac_addr`, `wan_mode`, `defroute_wan_ip`, `ipv6_info_buf` (`ip/prefijo`), `system{cpuLoad,total_mem,free_mem}`, cfg `4g_mode` |
| `infoInternet` | support_information_internet | `wan_connTime` (s), `wan_link_status=[['up','',''],null]`, cfg `wan_dns` (separado por espacios) |
| `infoFtth` | support_information_ftth | `traciver_status{phy_link,temp,volt,bias,tx_power,rx_power}`, `traffic_counter{…frames}`, `ont_pwd` (**secreto**) |
| `infoLan` | support_information_lan | `lan_status_list=[[n,'up'/'down','1G'/'100M'/'0M','FD'/'HD'],…,null]`, cfg `LogName0..4` (nombres de puerto), `lan_mac_addr`, `dhcp_leaseTime` |
| `clients` | network_connected | `online_client` (ver §6), `station_info.stations[]`, `topology_info.nodes[]`, cfg `client_mac<i>`/`client_hostname<i>` (nombres personalizados), `dhcp_client` |
| `wlan_combine` | wifi_main | cfg `wl_enable24G/5G`, `wl_ssid24G/5G`, `wifi_schedule_enable`, `wl_enable_change`, `curr_channel_24g/5g` (+ claves: **secreto**) |
| `wlan_guest` | wifi_guest | cfg `ssid_enable24G3`, `ssid_enable5G3`, `ssid_enable5G_H3`, `wl_ssid24G3` |
| `network_connected` | network_connected | `szSIP_Register_Status='<número> <1=registrado>|…'` |
| `remote_management_osp` | advanced_user_remote_access | cfg `rm_en`, `rm_port` (+ `remote_user`/`remote_pwd`: **secreto**) |
| `firewall_main` | advanced_firewall | cfg `firewall_enable`, `firewall_level` |

## 5. Escritura (`apply_abstract.cgi`)

```
POST /apply_abstract.cgi
Cookie: SID=…
Referer: http://<host>/<página origen>
Content-Type: application/x-www-form-urlencoded
```

| Campo            | Valor |
|------------------|-------|
| `action`         | `do_encode(<comando>)` |
| `httoken`        | token de la página origen |
| `submit_button`  | página a la que volver (`cPage` o la indicada en `next`) |
| `action_params`  | `do_encode(<parámetro>)` (solo si hay) |
| `805443298771`   | `do_encode(<gui_cehck_token>)`; valor en `global.js`: `addCfg("gui_cehck_token", "983272000000", "<n>")`. **El router lo rota tras cada orden**: hay que leer `global.js` justo antes de cada envío. Con un valor caducado el router corta la conexión sin aplicar nada. |
| `<id cfg>`       | `do_encode(<valor nuevo>)` por cada `addCfg` modificado |

Clave/IV del cifrado: los de la página origen.

### Operaciones implementadas

| Operación | Página origen | `action` | `action_params` | Cfg enviados |
|-----------|---------------|----------|-----------------|--------------|
| Reiniciar | `support_restart.htm` | `reboot` | `RebootFromGUI` | — (`submit_button=index.htm`) |
| WiFi on/off | `wifi_main.htm` | `ui_wireless` | — | `wl_enable24G`, `wl_enable5G`, `wl_enable_change=1`, y `wifi_schedule_enable=0` si estaba activa |
| WiFi invitados on/off | `wifi_guest.htm` | `ui_wireless` | — | `ssid_enable24G3`, `ssid_enable5G3`, `ssid_enable5G_H3` |
| Acceso remoto on/off (spec 002) | `advanced_user_remote_access.htm` | `ui_management` | `remote_management_mod` | `rm_en` |
| Acceso a Internet de un cliente (spec 004) | `network_access_schedule.htm` | `ui_parentalcontrol` | `mac_filter_mod` | `macFilter_active`, `macFilter_enable_<n>`, `macFilter_mac_<n>`, `macFilter_sch_<n>_<0-6>` |
| Nombre de un cliente (spec 004) | `network_customize.htm` | `ui_add_pclist` | `"<MAC>,<nombre>"` | `client_hostname<n>`, `client_mac<n>`, `client_deviceType<n>` |

> ⚠️ Causas de `Server disconnected` en `apply_abstract.cgi` (verificadas en vivo, spec 003):
> 1. la sesión ha sido expulsada por otro login (el router solo admite una sesión activa);
> 2. el *check token* está caducado (rota tras cada orden);
> 3. el router aún aplica la orden anterior (la web espera 20 s tras `ui_wireless`).
>
> `remaining_time` puede ser **negativo** (= sin bloqueo).

Antes de reiniciar, la web consulta `cgi/cgi_have_phone_call.js` (`query_have_call_status`)
y aborta si hay una llamada en curso.

## 6. `online_client` (19 columnas)

| # | Significado | Ejemplo |
|---|-------------|---------|
| 0 | nombre de host | `portatil-01` |
| 1 | IPv4 | `192.168.1.141` |
| 2 | MAC | `68:5e:dd:…` |
| 4 | origen (`LAN`, `24G`, `5G`, `5G_H`, `6G`) — en la práctica siempre `LAN` | |
| 5/6/7 | IPv6 GUA / LLA / ULA (`0` = vacío) | |
| 8 | `DHCP` / `Static` | |
| 9 | `Online` / `Offline` | |
| 10 | SSID | |
| 11 | DHCP option 60 (vendor class) | `android-dhcp-9` |
| 12 | último contacto `YYYY/MM/DD HH:MM:SS` | |
| 13 | tiempo conectado (s) | |
| 14 | interfaz física | `eth3.0` |
| 16 | MAC según lease DHCP | |
| 17 | nombre personalizado | |

El tipo real de conexión (Ether/24G/5G), la señal y la velocidad se obtienen de
`station_info.stations[]` (`connect_type`, `signal_strength`, `link_rate`,
`connect_ssid`).

## 7. Logout

`POST /logout.cgi` con `httoken` (+ `Referer`).

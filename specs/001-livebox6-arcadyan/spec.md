# Spec 001 — Integración HACS para Livebox 6 de Orange España (firmware Arcadyan)

| Campo        | Valor                                                        |
|--------------|--------------------------------------------------------------|
| Estado       | Implementada y validada en vivo (lectura y escrituras) con HA 2026.10 — ver specs 002 y 003 |
| Fecha        | 2026-10-24                                                   |
| Router base  | Livebox 6 Fibra (`ARLTFIBRA6`, HW `ARLTLBFIB61.0.0`, FW `02.03.01.035D build204`) |
| Dominio HA   | `orange_livebox_es`                                          |

## 1. Contexto y problema

El Livebox 6 que Orange instala en España (fabricado por Arcadyan) no expone ninguna API
documentada ni es compatible con la integración `livebox` existente (que usa la API
`sysbus` de los Livebox franceses de Sagemcom). Toda la información solo está accesible
desde la interfaz web `http://192.168.1.1`, protegida por un login con campos cifrados
(AES-CBC) y tokens anti-CSRF.

Queremos ver el estado del router y de la red doméstica en Home Assistant (presencia de
dispositivos, estado de la fibra, WAN, WiFi, telefonía) y poder ejecutar acciones básicas,
y dejar la puerta abierta a otros routers de Orange.

## 2. Historias de usuario

### US1 — Configurar el router desde la UI (P1)
Como usuario, quiero añadir el router indicando host, usuario y contraseña desde
*Ajustes → Dispositivos y servicios*, para no editar YAML.

**Aceptación**
1. *Dado* un host accesible y credenciales correctas, *cuando* envío el formulario,
   *entonces* se crea una entrada con título «Livebox 6 (`<serie>`)» y un dispositivo con
   modelo, fabricante, firmware, hardware y número de serie.
2. *Dada* una contraseña incorrecta, *entonces* el formulario muestra «Credenciales no
   válidas» y no se reintenta automáticamente.
3. *Dado* que el router está bloqueado por intentos fallidos, *entonces* el formulario
   muestra «Router bloqueado temporalmente, espera un minuto».
4. *Dado* un host inalcanzable o que no es un Livebox compatible, *entonces* se muestra
   «No se puede conectar» / «Router no compatible».
5. *Dado* que el mismo router (mismo nº de serie) ya está configurado, *entonces* el flujo
   aborta con «Ya configurado».

### US2 — Saber qué dispositivos están en casa (P1)
Como usuario, quiero un `device_tracker` por cada dispositivo conocido por el router para
automatizar presencia.

**Aceptación**
1. Cada MAC conocida genera un tracker (`source_type: router`) en estado `home` si el
   router la reporta *Online* y `not_home` en otro caso.
2. Atributos: IP, MAC, nombre de host, tipo de conexión (ethernet / wifi 2.4 GHz /
   wifi 5 GHz), SSID, señal (dBm), velocidad de enlace, interfaz, último contacto.
3. Las MAC duplicadas en la tabla del router se fusionan (gana la entrada *Online* o la
   más reciente).
4. Los dispositivos nuevos que aparezcan tras la configuración se añaden sin reiniciar HA.
5. Se usa el nombre personalizado que el usuario haya puesto en el router si existe.

### US3 — Monitorizar la conexión a Internet y la fibra (P1)

**Aceptación**
1. `binary_sensor` *Internet* (`connectivity`) = on si el enlace WAN está `up`.
2. `binary_sensor` *Enlace óptico* (`connectivity`) = on si `phy_link == 1`.
3. Sensores: IP pública IPv4, IPv6 WAN (si existe), modo WAN, servidores DNS (diagnóstico),
   *conectado desde* (`timestamp`).
4. Sensores ópticos (diagnóstico): potencia RX (dBm), potencia TX (dBm), temperatura del
   transceptor (°C), tensión (V), corriente de polarización (mA).
5. Contadores de tramas unicast RX/TX (`total_increasing`, deshabilitados por defecto).

### US4 — Estado del sistema (P2)

**Aceptación**
1. *Último arranque* (`timestamp`), carga de CPU (%), uso de memoria (%).
2. Nº de dispositivos conectados (total, por cable, por WiFi).
3. `binary_sensor` por puerto LAN (LAN1-4, los que muestra la web) con velocidad y dúplex como
   atributos (diagnóstico, deshabilitados por defecto).
4. Nivel de firewall y estado del acceso remoto (diagnóstico); el acceso remoto activado
   se marca como *problema* de seguridad.

### US5 — WiFi (P2)

**Aceptación**
1. Sensores: canal 2.4 GHz y canal 5 GHz (diagnóstico), SSID principal y de invitados.
2. `switch` *WiFi* que activa/desactiva ambas bandas exactamente como el botón de la web.
3. `switch` *WiFi de invitados* que activa/desactiva el SSID de invitados en ambas bandas.
4. Tras conmutar, el estado se refresca desde el router (no se asume optimista más allá
   del refresco).

### US6 — Telefonía (P3)

**Aceptación**
1. `binary_sensor` *Línea VoIP* registrada (`connectivity`) con el número como atributo.

### US7 — Reiniciar el router (P2)

**Aceptación**
1. `button` *Reiniciar* (`device_class: restart`) que envía la orden `reboot` igual que la web.
2. Mientras el router reinicia, las entidades pasan a *no disponible* y se recuperan solas.

### US8 — Soporte y diagnósticos (P2)

**Aceptación**
1. Descargar diagnósticos devuelve los datos normalizados y los CGI en bruto **sin
   secretos** (claves WiFi, PIN WPS, contraseña ONT, acceso remoto, IP pública, nº de
   teléfono, nº de serie).
2. Si la contraseña cambia, HA lanza un flujo de *reautenticación*.
3. Opciones: intervalo de sondeo (10–3600 s, por defecto 30 s).

## 3. Requisitos funcionales

| ID     | Requisito |
|--------|-----------|
| FR-001 | Autenticar contra `/login.cgi` replicando el cifrado de la web (ver `contracts/arcadyan-http.md`). |
| FR-002 | Mantener la sesión (`SID`) y re-autenticar de forma transparente ante redirección a `login.htm`. Si el re-login falla por credenciales → `ConfigEntryAuthFailed`. |
| FR-003 | Leer los CGI `router_status`, `info`, `infoInternet`, `infoFtth`, `infoLan`, `clients`, `wlan_combine`, `wlan_guest`, `network_connected`, `remote_management_osp`, `firewall_main` en cada ciclo, de forma secuencial. |
| FR-004 | Parsear los ficheros JS de los CGI sin ejecutar JavaScript (parser de literales propio). |
| FR-005 | Normalizar a modelos (`RouterData`) independientes del firmware. |
| FR-006 | Exponer las entidades descritas en US2–US7. |
| FR-007 | Las escrituras usan `apply_abstract.cgi` con los campos cifrados, el token de la página origen y el *check token* de la GUI. |
| FR-008 | Detectar el tipo de router a partir de `login.htm` (servidor `Arcadyan httpd`, `arc-crypt.js`) y elegir el driver. |
| FR-009 | Detectar el bloqueo por intentos fallidos (`remaining_time > 0`) y no enviar credenciales mientras dure. |
| FR-010 | Cerrar sesión (`logout.cgi`) al descargar la integración (best effort). |

## 4. Requisitos no funcionales

| ID      | Requisito |
|---------|-----------|
| NFR-001 | Sin dependencias externas nuevas: solo `aiohttp` y `cryptography`, ya incluidas en HA. |
| NFR-002 | Un ciclo de sondeo completo < 5 s en LAN y < 200 KB transferidos. |
| NFR-003 | Ningún secreto en entidades, atributos, logs ni diagnósticos (constitución III). |
| NFR-004 | La capa `api/` no importa nada de `homeassistant`. |
| NFR-005 | Cobertura de tests del parser y del protocolo con fixtures sintéticas. |
| NFR-006 | Compatible con HACS (`hacs.json`, `manifest.json` con `version`) y validable con `hassfest`. |
| NFR-007 | ~~El router admite sesiones concurrentes~~ **Falso** (spec 003): solo admite una sesión activa; HA cede la sesión cuando el usuario usa la web. |

## 5. Fuera de alcance (v0.1)

- Cambiar SSID/clave WiFi, reglas de firewall, NAT, DHCP estático.
- Registro de llamadas (el CGI `call_log` existe; formato pendiente de muestras reales).
- Programación WiFi, LEDs, USB/DLNA, espectro WiFi.
- Descubrimiento automático (DHCP/SSDP).
- Otros modelos (Livebox+ `ARPLUS6`, Livebox Infinity…): la arquitectura lo permite, se
  abordarán en specs posteriores con fixtures de cada modelo.

## 6. Preguntas abiertas / riesgos

| # | Tema | Mitigación |
|---|------|------------|
| 1 | Formato exacto de la respuesta de `apply_abstract.cgi` | Se considera éxito un 200/302 sin redirección a `login.htm`; se verifica releyendo el estado. Validar en vivo con el usuario. |
| 2 | El *check token* `gui_cehck_token` podría variar por firmware | Se lee dinámicamente de `/js/global.js` con valor por defecto de respaldo. |
| 3 | ¿Con qué rapidez marca el router un cliente como *Offline*? | Documentar; posible opción *consider_home* en una versión futura. |
| 4 | El Livebox+ (`ARPLUS6`) comparte la misma web (la propia web lo distingue por la versión de firmware) | Probable compatibilidad directa; requiere confirmación con un usuario de ese modelo. |

# Spec 004 — Gestión de dispositivos conectados (acceso a Internet, horarios, nombre)

| Campo   | Valor |
|---------|-------|
| Estado  | Implementada y validada en vivo (API y Home Assistant) |
| Fecha   | 2026-10-24 |
| Depende | Specs 001–003 |

## 1. Contexto

El usuario quiere gestionar los dispositivos de su red desde Home Assistant e incluso
**quitarles el acceso**. La web del router ofrece, por dispositivo (menú de cada equipo en
*Dispositivos conectados*):

| Función web | Página | Mecanismo |
|-------------|--------|-----------|
| **Programación de acceso** (control parental): *siempre permitido* / *siempre bloqueado* / *horario semanal por horas* | `network_access_schedule.htm?mac=<MAC>` | Filtro MAC del firewall: 16 huecos `macFilter_*` |
| **Personalizar**: nombre y tipo de icono | `network_customize.htm?mac=<MAC>` | Lista de clientes `client_*` (`ui_add_pclist`) |

### Formato del filtro (CGI `firewall_mac_filter`)

| Cfg | Valor |
|-----|-------|
| `macFilter_active` | `1` = control parental activo |
| `macFilter_enable_<n>` (n = 0…15) | `1` = regla activa |
| `macFilter_mac_<n>` | MAC en mayúsculas (la del *lease* DHCP si existe, como la web) |
| `macFilter_sch_<n>_<d>` (d = 0 lunes … 6 domingo) | 24 bits en hex (6 dígitos), bit más significativo = 00:00–01:00; `1` = permitido. `000000` = bloqueado todo el día, `FFFFFF` = permitido todo el día |

Envío: `apply_abstract.cgi` desde `network_access_schedule.htm`, `action=ui_parentalcontrol`,
`action_params=mac_filter_mod`, `submit_button=network_connected.htm`; la web espera 5 s.

- *Bloquear siempre*: `macFilter_active=1`, `enable=1`, `mac=<MAC>`, los 7 días `000000`.
- *Permitir siempre*: si había regla: `enable=0`, `mac=""`, los 7 días `""`.
- *Horario*: como bloquear pero con el hex de cada día.

Renombrar: desde `network_customize.htm`, `action=ui_add_pclist`,
`action_params="<MAC>,<nombre>"` (comillas dobles incluidas), cfg `client_hostname<n>`,
`client_mac<n>`, `client_deviceType<n>` (hueco existente de esa MAC o el primero libre). La
web prohíbe `' " \ / & \` $` en el nombre.

## 2. Historias de usuario

### US13 — Quitar/devolver el acceso a Internet a un dispositivo (P1)
**Aceptación**
1. Cada cliente rastreado (mismo criterio que los `device_tracker`) es un **dispositivo de
   HA** (conectado al router con `via_device`) con un `switch` *Acceso a Internet*.
2. `on` = sin restricción o con horario; `off` = bloqueado siempre.
3. Apagar = *bloquear siempre*; encender = *permitir siempre* (elimina el horario si lo había).
4. Atributos: `mode` (`allowed` / `blocked` / `scheduled`) y, si hay horario, el horario legible.
5. El tracker del cliente se agrupa en el mismo dispositivo de HA.
6. Si los 16 huecos están ocupados, error claro.

### US14 — Programar el acceso por horario (P2)
**Aceptación**
1. Acción `orange_livebox_es.set_access_schedule` sobre trackers del router, con un campo
   por día (`monday` … `sunday`) de franjas **permitidas** en horas, p. ej. `8-14,16-22`
   (fin exclusivo). `-` (o vacío) = bloqueado todo el día; día omitido = permitido todo el día;
   sin ningún día se elimina la restricción.
2. Validación: horas 0–24, inicio < fin; error claro si no.

### US15 — Renombrar un dispositivo en el router (P2)
**Aceptación**
1. Acción `orange_livebox_es.set_device_name` sobre trackers del router, con `name`.
2. Se rechazan los caracteres que rechaza la web.
3. El nombre se refleja en el router (y en el siguiente ciclo, en HA).

## 3. Requisitos

| ID     | Requisito |
|--------|-----------|
| FR-401 | Se lee el CGI `firewall_mac_filter` en cada ciclo (≈ 7 KB). |
| FR-402 | `ConnectedDevice.access_mac` = MAC del lease DHCP si existe; si no, la MAC. |
| FR-403 | `RouterData.access_rules`: MAC → regla (hueco, modo, horario de 7 días). |
| FR-404 | Escrituras con `force=True` y reintento por router ocupado (spec 003). Asentamiento 5 s. |
| FR-405 | Acciones registradas en `async_setup` con `async_register_platform_entity_service` (HA ≥ 2025.10). |
| FR-406 | Constitución II: solo se envía lo que enviaría la web. Constitución III: las MAC de las reglas se redactan en diagnósticos. |

## 4. Fuera de alcance
- Borrar dispositivos olvidados del histórico del router.
- Cambiar el tipo de icono (se conserva el actual o `desktop`, como la web).
- Reglas del firewall por puertos/IP.

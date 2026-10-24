# Spec 006 — Control de los LED del router

| Campo   | Valor |
|---------|-------|
| Estado  | **Descartada** para el Livebox 6: la función no tiene efecto (ver §4) |
| Fecha   | 2026-10-24 |
| Depende | Specs 001, 003, 004 (formato de horario) |

## 1. Hallazgo

La página *Estado de los LED* (`support_leds.htm`) es **solo informativa**, pero el firmware
incluye una página **no enlazada en el menú**, `led_scheduling.htm` («LEDs planner»), con su
CGI `cgi_led_schedule.js` y el comando `subFormRestartLedSch = "ui_led_scheduler"`
(`js/subformvar.js`). Es una página oficial de la web del router: la integración envía
exactamente lo que envía ella (constitución II).

| Cfg | Valor |
|-----|-------|
| `led_sch_enable` | `0` = «Activar los LED permanentemente: **Sí**»; `1` = **No**: se aplica el horario. Vacío (sin configurar) = LED encendidos |
| `led_sch0` … `led_sch6` | Lunes … domingo. 24 bits en hex (bit alto = 00:00); `1` = LED **encendido** esa hora, `0` = apagado (`hr_divided = 1`) |

Envío: `apply_abstract.cgi` desde `led_scheduling.htm`, `action=ui_led_scheduler`, sin
`action_params`; la web espera 5 s. Estado actual de cada LED: `cgi_led_osp.js`
(`leds_status = [{'internet':['white','on']}, …]`).

## 2. Historias de usuario

### US17 — Apagar/encender los LED (P1)
**Aceptación**
1. `switch` *LED* (categoría configuración). `on` = encendidos (siempre o con horario);
   `off` = apagados siempre.
2. Apagar = horario con los 7 días `000000`; encender = «Activar permanentemente: Sí»
   (el horario guardado se conserva, como en la web).
3. Atributos: `mode` (`on` / `off` / `scheduled`), `schedule` si hay horario e
   `indicators` (color encendido de cada LED: internet, wifi, voz…).

### US18 — Modo noche programado (P2)
**Aceptación**
1. Acción `orange_livebox_es.set_led_schedule` sobre el switch *LED*, con las horas en las que
   los LED están **encendidos** por día (mismo formato que `set_access_schedule`:
   `8-23`, `-` = apagados todo el día, día omitido = encendidos todo el día; sin días =
   encendidos permanentemente).
2. Usarla sobre otro switch da un error claro.

## 3. Requisitos

| ID     | Requisito |
|--------|-----------|
| FR-601 | Se leen `led_schedule` y `led_osp` en cada ciclo (< 1 KB). |
| FR-602 | `RouterData.leds: LedStatus | None` (`schedule_enabled`, `schedule`, `indicators`, `mode`). |
| FR-603 | `Feature.LED_CONTROL`; escrituras con `force=True`, reintento por router ocupado y asentamiento 5 s (spec 003). |
| FR-604 | Validación en vivo: apagar → comprobar → encender; y un horario → restaurar. |

## 4. Resultado de la validación en vivo (2026-10-24) — DESCARTADA

| Prueba | Resultado |
|--------|-----------|
| Apagar (horario `000000` × 7) | El router **acepta y guarda** la configuración (`led_sch_enable=1`) |
| Horario `8-23` y vuelta a «permanentemente» | Aceptado y guardado |
| `led_osp` (estado de los LED) durante 75 s con los LED «apagados» | Sin cambios: siempre verdes |
| **Comprobación física por el usuario** | **Los LED siguen encendidos** |

Conclusión: `led_scheduling.htm` existe en el firmware (probablemente pensada para otros
modelos que comparten firmware), pero **no actúa sobre el hardware del Livebox 6**. Por la constitución II no se expone un
control que no funciona: el código se retiró. Se restauró la configuración del router a
«LED permanentemente encendidos» (`led_sch_enable=0`) para que una futura actualización de
firmware no active un horario de apagado guardado durante las pruebas.

Si otro modelo (Livebox 7…) muestra «LEDs planner» en su menú, esta spec documenta el
protocolo completo para implementarlo.

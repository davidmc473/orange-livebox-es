# Spec 003 — Convivencia con la web del router (sesión única)

| Campo   | Valor |
|---------|-------|
| Estado  | Implementada |
| Fecha   | 2026-10-24 |
| Corrige | Spec 001 (NFR-007 era falso) |

## 1. Hallazgo

Experimento controlado (2026-10-24, misma IP):

| Paso | Resultado |
|------|-----------|
| Cliente X (User-Agent «Chrome») inicia sesión | OK |
| Cliente Y (User-Agent «HomeAssistant») inicia sesión | OK |
| X hace una petición | **302 → login.htm**: X ha sido expulsado |

Con el **mismo** User-Agent ambas sesiones conviven (por eso la exploración inicial
concluyó erróneamente que había sesiones concurrentes). En la práctica, **el router solo
admite una sesión de administración activa**: un login desde otro navegador/programa
expulsa al anterior y, en algunos momentos, el router **rechaza** el login nuevo con el
mismo error que una contraseña incorrecta (`login.htm?err=1`).

Consecuencias observadas con la v0.1:
- Al entrar el usuario en la web, HA era expulsado; 30 s después HA volvía a entrar y
  expulsaba al usuario («a veces me dice que la contraseña es incorrecta»).
- Un login de HA rechazado por esta causa se trataba como credenciales no válidas →
  reautenticación falsa y sondeo detenido.
- Las escrituras enviadas con una sesión ya expulsada hacen que el router corte la
  conexión (`Server disconnected`) sin aplicar nada. Sin interferencias, WiFi, WiFi de
  invitados y acceso remoto funcionan (verificado en vivo en ambos sentidos).

## 2. Historias de usuario

### US11 — Poder usar la web del router con la integración activa (P1)
**Aceptación**
1. Si HA detecta que otra sesión le ha expulsado, **cede la sesión**: deja de iniciar
   sesión durante un *tiempo de cesión* configurable (por defecto 10 min, igual que el
   tiempo de inactividad de la web) y sus entidades pasan a *no disponible* con un motivo
   claro en el log.
2. Pasado ese tiempo, HA vuelve a entrar (si el usuario sigue en la web, será expulsado
   en ese momento; se documenta).
3. Un login rechazado **después** de haber entrado con éxito alguna vez con esas mismas
   credenciales no se considera contraseña incorrecta, sino conflicto de sesión → cede.
   Solo en el primer login (alta, reautenticación) un rechazo significa credenciales no
   válidas.
4. Si los rechazos persisten durante más de 1 hora (3 intentos espaciados por la cesión), se
   escala a credenciales no válidas → reautenticación (el usuario pudo cambiar la clave).

### US12 — Las órdenes explícitas funcionan aunque HA esté cediendo (P1)
**Aceptación**
1. Pulsar un switch/botón en HA inicia sesión aunque haya otra activa (expulsándola) y
   ejecuta la orden; tras el éxito termina la cesión.
2. Si una escritura recibe un corte de conexión y la sesión resulta expulsada, se vuelve a
   iniciar sesión y se reintenta **una** vez (las órdenes son idempotentes: fijar on/off).
3. En el reinicio, un corte de conexión tras enviar la orden se considera éxito (el router
   se está reiniciando) y no se reintenta.

## 3. Requisitos

| ID     | Requisito |
|--------|-----------|
| FR-301 | Nueva excepción `SessionConflict` (otra sesión activa o login rechazado tras haber funcionado). |
| FR-302 | Expulsión = `SessionExpired` cuando la última petición correcta fue hace menos de 8 min (la web caduca a los 10); si fue antes, es caducidad normal y se reabre la sesión. |
| FR-303 | El coordinador, ante `SessionConflict`, no contacta con el router hasta que pase el tiempo de cesión. |
| FR-304 | Opción *Tiempo de cesión de la sesión* (1–60 min, por defecto 10). |
| FR-305 | Las escrituras usan `force=True`: reabren sesión y reintentan una vez. |
| FR-306 | El router falso de los tests emula la sesión única por User-Agent. |
| FR-307 | Tras cada orden, el router necesita asentarse (la web espera `wait`: 20 s tras `ui_wireless`, 5 s tras `ui_management`); una orden enviada antes recibe un corte de conexión **con la sesión aún válida** (observado en vivo). El cliente espera ese tiempo antes de la siguiente orden. |
| FR-309 | El *check token* de la GUI (`gui_cehck_token` en `global.js`) **rota tras cada orden** (observado en vivo: el valor de `global.js` cambia tras cada orden). Se lee justo antes de cada orden, sin caché; el nombre del campo también se lee de `global.js`. Era la causa de que la segunda orden de una misma sesión fallase siempre. |
| FR-308 | Si aun así una orden recibe un corte con la sesión válida, se reintenta una vez tras 10 s, recalculando los cambios (si ya se aplicó, no se reenvía). |

## 4. Fuera de alcance
- Detectar si el usuario sigue en la web sin expulsarle (el router no lo expone).

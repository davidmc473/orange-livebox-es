# Spec 002 — Control del acceso remoto y entidades activas por defecto

| Campo   | Valor |
|---------|-------|
| Estado  | Implementada y validada en vivo |
| Fecha   | 2026-10-24 |
| Depende | Spec 001 |

## 1. Contexto

El usuario quiere poder **activar y desactivar el acceso remoto** a la web del router
(*Configuración avanzada → Acceso remoto*). En la spec 001 solo se mostraba como
`binary_sensor` de problema. Además, varias entidades salían deshabilitadas por defecto y
el usuario prefiere verlas activas.

## 2. Historias de usuario

### US9 — Activar/desactivar el acceso remoto (P1)
**Aceptación**
1. Existe un `switch` *Acceso remoto* (categoría configuración) cuyo estado refleja `rm_en`.
2. Al conmutarlo se envía exactamente lo que envía la web al guardar ese formulario
   cambiando solo la casilla *activar*: no se modifican usuario, contraseña ni puerto.
3. Atributo `port` con el puerto configurado. Nunca se exponen usuario ni contraseña.
4. Sustituye al `binary_sensor` *Acceso remoto* de la spec 001 (dejaría de ser coherente
   tener las dos entidades).

### US10 — Entidades activas por defecto (P2)
**Aceptación**
1. Todas las entidades del router se crean habilitadas.
2. La *IPv6 WAN* solo se crea si la línea tiene IPv6 (si no, sería siempre «desconocida»).
3. Los rastreadores siguen la opción *Activar automáticamente los rastreadores nuevos*.

## 3. Requisitos

| ID     | Requisito |
|--------|-----------|
| FR-201 | Escritura desde `advanced_user_remote_access.htm`: `action=ui_management`, `action_params=remote_management_mod`, cfg `rm_en` (solo si cambia). |
| FR-202 | `Feature.REMOTE_ACCESS_SWITCH` en el driver Arcadyan. |
| FR-203 | Constitución III: `remote_user`/`remote_pwd` no salen del cliente. |

## 4. Riesgos

| Riesgo | Mitigación |
|--------|------------|
| Las escrituras fallaban en vivo con «Server disconnected» | Resuelto en la spec 003 (sesión única + *check token* rotatorio). |

# Constitución del proyecto «Orange Livebox ES» para Home Assistant

Principios que gobiernan todas las especificaciones, planes y tareas de este repositorio.
Cualquier spec o plan que los contradiga debe justificarlo explícitamente en su sección
«Complejidad / excepciones».

## I. Spec primero (SDD)

Ningún cambio funcional entra sin una especificación en `specs/NNN-nombre/`:
`spec.md` (qué y por qué) → `plan.md` (cómo) → `tasks.md` (pasos verificables).
El código sigue a la spec; si la implementación descubre algo que la contradice, se
actualiza primero la spec.

## II. Solo lectura por defecto, escritura explícita y segura

- La integración **nunca** modifica la configuración del router salvo por una acción
  explícita del usuario (switch o botón).
- Las acciones de escritura replican exactamente lo que envía la interfaz web oficial
  (mismos campos, mismo comando). Nada de parámetros inventados.
- Las acciones disruptivas (reinicio) no deben ejecutarse en automático en los tests en vivo.

## III. Secretos fuera de las entidades y de los logs

Claves WiFi, PIN WPS, contraseña del ONT, contraseña de acceso remoto y credenciales de
administración **nunca** se exponen como entidades ni atributos, ni aparecen en logs.
Los diagnósticos los redactan. Las fixtures de test son sintéticas o anonimizadas.

## IV. Arquitectura multi-modelo

El acceso al router vive en una capa `api/` sin dependencias de Home Assistant, detrás de
una interfaz abstracta (`LiveboxClient`). Cada familia de firmware es un *driver*
(p. ej. `arcadyan`). Home Assistant solo consume modelos normalizados (`RouterData`), de
forma que añadir otro router Orange sea añadir un driver + fixtures, sin tocar entidades.

## V. Respeto al router

- Un único coordinador por router, sondeo configurable (por defecto 30 s, mínimo 10 s).
- Peticiones secuenciales (el httpd embebido es limitado), reutilizando la sesión.
- Re-login transparente cuando la sesión caduca; nunca más de un intento de login fallido
  seguido sin intervención del usuario (el router bloquea tras 3 fallos).

## VI. Testeable sin router

Toda la lógica de parseo y protocolo se prueba con fixtures. El test en vivo
(`scripts/live_probe.py`) es opcional y lee las credenciales de variables de entorno.

## VII. Estándares Home Assistant

Config flow (sin YAML), `DataUpdateCoordinator`, `has_entity_name`, traducciones en/es,
`device_class`/`state_class`/`entity_category` correctos, diagnósticos, reauth y
compatibilidad HACS.

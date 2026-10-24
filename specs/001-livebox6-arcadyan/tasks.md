# Tareas 001 — Livebox 6 (Arcadyan)

Leyenda: `[x]` hecho · `[ ]` pendiente · `[~]` requiere validación del usuario.
`[P]` = paralelizable. Cada tarea referencia la historia / requisito que satisface.

## Fase 0 — Investigación
- [x] T001 Explorar web del router, CGI y mecanismo de login (research.md)
- [x] T002 Documentar protocolo (contracts/arcadyan-http.md)
- [x] T003 Prototipo de login y lectura de CGI contra el router real

## Fase 1 — Esqueleto del repositorio
- [x] T010 Estructura `custom_components/orange_livebox_es/`, `manifest.json`, `hacs.json`
- [x] T011 [P] `README.md`, `LICENSE`, `.gitignore`, `pyproject.toml` (pytest)
- [x] T012 [P] Workflow CI: hassfest + validación HACS + pytest

## Fase 2 — Capa API (sin HA) — FR-001…FR-005, FR-008…FR-010
- [x] T020 `api/exceptions.py`, `api/models.py`, `api/base.py`
- [x] T021 `api/jsparse.py` (literales JS, `addCfg`, reasignaciones) + tests
- [x] T022 `api/crypto.py` (material de página, `do_encode`/`do_decode`, campos login) + tests
- [x] T023 `api/arcadyan/parser.py` (CGI → `RouterData`) + tests con fixtures sintéticas
- [x] T024 `api/arcadyan/client.py` (login, lockout, SID, relogin, CGI con Referer, logout)
- [x] T025 Escrituras: reinicio, WiFi, WiFi invitados (`apply_abstract.cgi`) — FR-007
- [x] T026 `api/__init__.py::async_create_client` con detección de driver — FR-008
- [x] T027 `tests/fake_router.py` + tests de protocolo (login, Referer, relogin, lockout, escrituras)
- [x] T028 `api/redact.py` y lista de secretos — NFR-003

## Fase 3 — Integración Home Assistant
- [x] T030 `const.py`, `coordinator.py`, `entity.py`, `__init__.py` (runtime_data, unload, logout)
- [x] T031 `config_flow.py`: user, reauth, options (US1, US8)
- [x] T032 [P] `sensor.py` (US3, US4, US5)
- [x] T033 [P] `binary_sensor.py` (US3, US4, US6)
- [x] T034 [P] `device_tracker.py` con altas dinámicas (US2)
- [x] T035 [P] `switch.py` WiFi + invitados (US5)
- [x] T036 [P] `button.py` reinicio (US7)
- [x] T037 `diagnostics.py` con redacción (US8)
- [x] T038 `strings.json`, `translations/en.json`, `translations/es.json`, `icons.json`
- [x] T039 Tests del config flow y del setup (pytest-homeassistant-custom-component, en Docker)

## Fase 4 — Validación
- [x] T040 `scripts/live_probe.py` (solo lectura) contra el router real — login 0,3 s, ciclo 2,5 s
- [x] T041 Home Assistant 2026.10 real en Docker (`docker-compose.dev.yml`) contra el router:
      entrada `loaded`, 18 trackers, sin errores en log, ciclos de 2,4–3,0 s, diagnósticos
      reales revisados sin secretos (se corrigió la fuga de `device_id`/`parent_id`)
- [x] T046 hassfest sin errores · ruff limpio · 65 tests con arnés HA + 59 de protocolo
- [x] T042 Switch *WiFi de invitados* en vivo ✅ (on/off, también 3 órdenes seguidas desde HA).
      El fallo inicial se debía a la sesión única y al *check token* rotatorio (spec 003)
- [x] T043 Botón *Reiniciar* en vivo desde HA ✅ — web de vuelta a los 232 s, HA recuperado solo a los 309 s
- [x] T044 Switch *WiFi* en vivo ✅ (off → on)
- [x] T047 Corrección: se exponía «Puerto 2.5G LAN», que el Livebox 6 español no tiene. Solo LAN1–LAN4
      (como la web) y se borra la entidad sobrante en instalaciones existentes
- [ ] T045 Publicar repositorio en GitHub y añadirlo como repositorio personalizado en HACS

## Backlog (specs futuras)
- [x] Spec 002: control del acceso remoto + entidades activas por defecto (`specs/002-acceso-remoto/`)
- [x] Spec 003: convivencia con la web del router — sesión única (`specs/003-convivencia-sesion/`)
- [x] Spec 004: gestión de dispositivos — acceso a Internet, horarios y nombre (`specs/004-gestion-dispositivos/`)
- [x] Spec 005: descubrimiento automático por DHCP/ARP (`specs/005-descubrimiento/`)
- [ ] Spec 006: Livebox+ (`ARPLUS6`) — confirmar compatibilidad con fixtures de un usuario
- [ ] Spec 007: registro de llamadas (`call_log`) como sensor / evento
- [ ] Spec 008: otros routers Orange ES (Livebox Infinity, Livebox Fibra antiguo)

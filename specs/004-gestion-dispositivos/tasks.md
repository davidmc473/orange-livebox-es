# Tareas 004 — Gestión de dispositivos

- [x] T401 Analizar `network_access_schedule.htm` (filtro MAC/horarios) y `network_customize.htm` (nombre)
- [x] T402 `api/schedule.py`: franjas legibles ↔ hex de 24 bits (bit alto = 00:00)
- [x] T403 Modelos `AccessRule`/`AccessMode`, `ConnectedDevice.access_mac`/`device_type`; parser del CGI `firewall_mac_filter`
- [x] T404 Cliente: `async_set_device_access` (bloquear / horario / permitir) y `async_set_device_name`
- [x] T405 Validación en vivo con la API sobre un equipo desconectado (una consola sin usar): bloquear → horario → permitir y renombrar → restaurar
- [x] T406 `clients.py`: cada cliente gestionado es un dispositivo de HA (`via_device_id` del router) con tracker + switch
- [x] T407 Switch *Acceso a Internet* por cliente (atributos `mode`, `schedule`)
- [x] T408 Acciones `set_device_name` y `set_access_schedule` (`async_register_platform_entity_service`), `services.yaml`, traducciones e iconos
- [x] T409 Tests: horarios, parser, protocolo (router falso) y HA — 107 + 95 en verde; hassfest y ruff limpios
- [x] T410 HA real: 17 switches de acceso creados, acciones registradas, sin avisos (se corrigió `via_device` obsoleto)
- [x] T411 Bloqueo de un dispositivo conectado desde HA: probado por el usuario ✅ y por Claude con una
      bombilla (bloquear → `blocked` en el router → permitir → `allowed`). El router tarda unos
      segundos en reflejar el cambio; el switch lo cubre con el estado asumido

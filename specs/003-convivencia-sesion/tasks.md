# Tareas 003 — Convivencia con la web del router

- [x] T301 Experimento controlado: dos clientes con distinto User-Agent → el segundo expulsa al primero
- [x] T302 `SessionConflict`, detección expulsión vs caducidad (`KICK_WINDOW`), escalado a `InvalidAuth`
- [x] T303 Coordinador: cesión de la sesión (opción 1–60 min, por defecto 10); controles operables durante la cesión
- [x] T304 Órdenes con `force=True` (reabren sesión y reintentan una vez) y reinicio tolerante al corte
- [x] T305 FR-307: espera de asentamiento entre órdenes (20 s `ui_wireless`, 5 s `ui_management`)
- [x] T306 FR-309: *check token* leído antes de cada orden (rota tras cada orden) — causa raíz del fallo de T042
- [x] T307 Router falso: sesión única por UA, rechazos, corte con sesión expulsada, router ocupado, token rotatorio
- [x] T308 Sesión HTTP compartida (`session.py`): HA ya no avisa de que se cierra su sesión aiohttp
- [x] T309 Validación en vivo (HA 2026.10 + router real, 2026-10-24):
      - login simulado de un navegador → HA cede, la sesión del navegador sigue viva
      - orden durante la cesión → HA recupera la sesión, aplica y sale de la cesión
      - 3 órdenes seguidas de WiFi invitados desde HA → las 3 aplicadas (esperas de ~16 s)
      - reinicio desde HA → caída a los 16 s, web a los 232 s, HA recuperado solo a los 309 s

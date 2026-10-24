# Tareas 005 — Descubrimiento automático

- [x] T501 Investigar vías: SSDP (UPnP desactivado), mDNS (no), DHCP/ARP + PTR (`Livebox`, OUI `60:8D:26`) ✅
- [x] T502 `api.async_probe_router()` → `RouterProbe(driver, is_livebox, model)` con una sola petición sin credenciales
- [x] T503 `manifest.json`: `dhcp` → `hostname: livebox*` y `macaddress: 608D26*`
- [x] T504 `async_step_dhcp` + `async_step_discovery_confirm` (dedup. por MAC, `not_supported` silencioso, `already_configured`)
- [x] T505 Traducciones en/es (`flow_title`, `discovery_confirm`, abortos)
- [x] T506 Tests: sonda (Livebox / otro Arcadyan) y flujo DHCP (ok, no soportado, ya configurado, duplicado)
- [x] T507 En vivo: la sonda reconoce el router real como «Livebox 6»; los *matchers* casan con su PTR y su MAC
- [ ] T508 Comprobar en la instancia HA del usuario que aparece la tarjeta «Descubierto» (el HA de pruebas en Docker Desktop no ve la ARP de la LAN)

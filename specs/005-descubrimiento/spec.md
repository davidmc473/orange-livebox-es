# Spec 005 — Descubrimiento automático del router

| Campo   | Valor |
|---------|-------|
| Estado  | Implementada — pendiente de verlo en la instancia HA del usuario (T508) |
| Fecha   | 2026-10-24 |
| Depende | Spec 001 |

## 1. Investigación (2026-10-24, red del usuario)

| Vía de HA | Resultado |
|-----------|-----------|
| SSDP / UPnP | ❌ El router no anuncia nada: UPnP desactivado (puertos UPnP habituales cerrados). |
| zeroconf / mDNS | ❌ El firmware Arcadyan no anuncia servicios mDNS. |
| **DHCP** (*NetworkWatcher*: tabla ARP + nombre inverso) | ✅ El router está en la tabla ARP de cualquier equipo (es la puerta de enlace) con MAC `60:8D:26:C2:4F:14` (OUI Arcadyan) y su DNS resuelve el inverso de `192.168.1.1` como **`Livebox`**. |

> El router no hace peticiones DHCP (es el servidor), pero el vigilante de red de HA
> descubre también por ARP/PTR, que es lo que se aprovecha.

## 2. Historias de usuario

### US16 — Descubrir el Livebox sin escribir la IP (P2)
**Aceptación**
1. Al aparecer en la red un equipo con nombre `livebox*` **o** MAC con OUI `60:8D:26`, HA
   lanza el flujo de la integración.
2. El flujo comprueba **sin credenciales** que `login.htm` es una web Arcadyan **de Livebox**
   (contiene «Livebox»). Si no lo es, aborta en silencio (`not_supported`): otros routers
   Arcadyan (de otros operadores) o Livebox franceses (Sagemcom) no muestran nada.
3. Si ya existe una entrada con ese host, aborta (`already_configured`).
4. HA muestra la tarjeta *Descubierto* con el nombre del modelo y la IP; al confirmarla solo
   se pide usuario (por defecto `admin`) y contraseña.
5. Tras el login, el `unique_id` es el número de serie como en el alta manual (no se
   duplican entradas); si ya existía con otra IP, se actualiza el host.

## 3. Requisitos

| ID     | Requisito |
|--------|-----------|
| FR-501 | `manifest.json` → `"dhcp": [{"hostname": "livebox*"}, {"macaddress": "608D26*"}]`. |
| FR-502 | `api.async_probe_router()` devuelve driver y si la web es de un Livebox (y el modelo si se reconoce), con una sola petición. |
| FR-503 | Flujos de descubrimiento repetidos para el mismo equipo se deduplican (`unique_id` temporal = MAC). |
| FR-504 | Textos en/es: título del flujo `{name}`, paso `discovery_confirm`. |

## 4. Fuera de alcance
- Activar UPnP en el router para descubrir por SSDP.

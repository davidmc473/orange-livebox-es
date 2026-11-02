# Spec 007 — Sensores por dispositivo (señal y velocidad de enlace)

| Campo   | Valor |
|---------|-------|
| Estado  | Implementada y validada en vivo |
| Fecha   | 2026-11-02 |
| Depende | Specs 001, 002, 004 |

## 1. Contexto

El `device_tracker` de cada cliente ya muestra la señal WiFi y la velocidad de enlace, pero
como **atributos**: no se pueden representar con la tarjeta de historial ni generan
estadísticas a largo plazo. Convertirlos en sensores permite ver cuándo empeora la conexión
de un dispositivo y usarlo en automatizaciones.

No hace falta leer nada nuevo del router: los datos ya llegan en el CGI `clients` en cada
ciclo.

## 2. Historias de usuario

### US19 — Ver la calidad de la conexión de un dispositivo con histórico (P1)
**Aceptación**
1. Cada cliente gestionado (mismo criterio que el `device_tracker`, spec 004) tiene un
   sensor *Velocidad de enlace* en Mbit/s.
2. Los clientes vistos por WiFi tienen además un sensor *Intensidad de señal* en dBm. Los
   que solo han usado cable no lo tienen: sería una entidad siempre «desconocida» (mismo
   criterio que la *IPv6 WAN*, spec 002 US10).
3. Si un cliente que usaba cable se conecta por WiFi, su sensor de señal se crea en ese
   ciclo, sin recargar la integración.
4. Con el cliente desconectado, los sensores valen `unknown`: nunca el último valor conocido.
5. Si el router no responde o HA le está cediendo la sesión (spec 003), valen `unavailable`.
6. Un sensor ya creado sobrevive a un reinicio de HA aunque el cliente esté desconectado.
7. Los atributos actuales del `device_tracker` no cambian.

## 3. Requisitos

| ID     | Requisito |
|--------|-----------|
| FR-701 | Sin peticiones nuevas: se usan `ConnectedDevice.signal_strength` y `link_rate_mbps`. |
| FR-702 | `unique_id` = `<mac>_<clave>`; la entidad se agrupa en el dispositivo de HA del cliente por su MAC. |
| FR-703 | `state_class: measurement` (estadísticas a largo plazo) y categoría *diagnóstico*. |
| FR-704 | Deshabilitados por defecto (ver §4). |

## 4. Decisiones

- **Deshabilitados por defecto.** Es una excepción a la preferencia de la spec 002 (US10):
  aquella regla cubre las entidades *del router*, y estas son de los clientes. La señal y
  la velocidad WiFi pueden cambiar en cada sondeo: con el intervalo de 30 s, cada cliente
  añadiría hasta 5.760 estados al día a la base de datos. El usuario activa los que quiera,
  también en bloque desde *Ajustes → Entidades*. Propuesto así y aceptado antes de implementar.
- **`unknown` y no `unavailable` para un cliente desconectado.** El router ha respondido;
  lo que no existe es la medida. `unavailable` queda para los fallos de lectura.
- **Datos caducados.** El router conserva `signal_strength` y `link_rate` de las estaciones
  con `online: 0`, por lo que el sensor comprueba `ConnectedDevice.connected` antes de dar
  un valor.

## 5. Fuera de alcance

- Sensor del tipo de conexión o banda: sigue siendo un atributo del `device_tracker`.
- Señal mínima/máxima y velocidad máxima: exigirían leer además `cgi_wifi_client` en cada ciclo.
- Una opción para crear todos estos sensores ya habilitados.

## 6. Validación en vivo (2026-11-02)

Sobre el HA de desarrollo con el router real, con los sensores activados y 4 minutos de sondeo:

| Prueba | Resultado |
|--------|-----------|
| Sensores creados | 22 en 21 clientes: 21 de velocidad y 1 de señal |
| Valores | Señal −57 dBm; velocidad entre 544 y 1000 Mbit/s |
| Clientes desconectados | 2, ambos en `unknown` |
| Conectado sin velocidad | 1: no figura en `station_info` y su sensor queda en `unknown` |
| Errores o avisos de la integración en el log | 0 |

## 7. Limitación: clientes detrás de otro equipo

El router solo mide lo que conecta directamente a él. Un cliente detrás de un switch o de un
punto de acceso externo figura como `Ether`: no tiene sensor de señal y su *velocidad de
enlace* es la del puerto del router, no la del dispositivo.

En la red de pruebas, 14 de los 19 clientes conectados están en `eth3.0`, todos a
`1000Mbps`, y ninguno aparece en `cgi_wifi_client`. No es un error de detección: es lo que
declara el router.

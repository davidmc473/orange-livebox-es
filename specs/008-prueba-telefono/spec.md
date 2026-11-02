# Spec 008 — Hacer sonar el teléfono fijo

| Campo   | Valor |
|---------|-------|
| Estado  | Implementada y validada en vivo |
| Fecha   | 2026-11-02 |
| Depende | Specs 001, 003 |

## 1. Hallazgo

La página *Mi teléfono* (`phones.htm`, en el menú de la web) tiene un botón oficial **test**
para comprobar que el teléfono conectado al Livebox funciona:

```js
function test_phone(){
  return subForm({frm:document.tF, cmd:subFormVoRingTest, wait:2});}
// js/subformvar.js: var subFormVoRingTest='ui_voip_ring_test_osp';
```

| Campo | Valor |
|-------|-------|
| Página origen | `phones.htm` |
| `action` | `ui_voip_ring_test_osp` |
| `action_params` | — |
| Cfg enviados | Ninguno: no cambia la configuración del router |
| Espera | 2 s (`wait`) |

## 2. Historias de usuario

### US20 — Hacer sonar el teléfono desde Home Assistant (P1)
**Aceptación**
1. Botón *Hacer sonar el teléfono* en el dispositivo del router, de categoría *diagnóstico*.
2. Solo existe si el router tiene alguna línea de voz: sin línea no hay teléfono que probar.
3. Pulsarlo envía exactamente lo que envía el botón *test* de la web (constitución II).
4. Se puede usar en automatizaciones con `button.press`.
5. Sigue operativo mientras HA cede la sesión (spec 003, US12), como el botón de reinicio.

## 3. Requisitos

| ID     | Requisito |
|--------|-----------|
| FR-801 | `Feature.RING_TEST` en el driver Arcadyan y `LiveboxClient.async_ring_test()`. |
| FR-802 | Orden con `force=True`, reintento por router ocupado y asentamiento de 2 s (spec 003). |
| FR-803 | Validación en vivo con comprobación física: que el usuario oiga sonar el teléfono (la spec 006 demostró que el router puede aceptar una orden sin ejecutarla). |

## 4. Decisiones

- **Se reintenta si el router está ocupado**, como las demás órdenes. Si la conexión se corta
  tras llegar la orden, el teléfono podría sonar dos veces; es preferible a no avisar cuando
  se usa en una automatización.
- **No se comprueba si hay una llamada en curso.** La web lo hace para reiniciar, pero no en
  este botón, y solo se envía lo mismo que ella.

## 5. Fuera de alcance

- Elegir qué teléfono o línea suena, y durante cuánto: la web no ofrece esas opciones.
- Marcación automática (*Autodial*) y asignación de puertos y líneas de la misma página.
- Registro de llamadas.

## 6. Validación en vivo (2026-11-02)

| Prueba | Resultado |
|--------|-----------|
| Orden enviada una vez con el driver al router real | Aceptada (HTTP 200) en 0,3 s |
| **Comprobación física por el usuario** | **El teléfono ha sonado** |

La duración del timbre no se midió. El botón de HA está cubierto por los tests; la prueba en
vivo usó directamente `async_ring_test()`, que es lo que ejecuta el botón.

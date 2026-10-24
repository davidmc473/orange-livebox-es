# Orange Livebox (España) para Home Assistant

Integración personalizada (HACS) para los routers que Orange instala en España.
Primer modelo soportado: **Livebox 6 Fibra** (Arcadyan `ARLTFIBRA6`), probado con el
firmware `02.03.01.035D build204`. La arquitectura admite añadir más modelos Orange.

> No es un producto oficial de Orange ni de Arcadyan.

## Qué ofrece

| Tipo | Entidades |
|------|-----------|
| **Presencia** | Un `device_tracker` por cada dispositivo visto conectado (IP, MAC, tipo de conexión, SSID, señal, velocidad de enlace) |
| **Control de dispositivos** | Cada cliente es un dispositivo de HA con un switch **Acceso a Internet** (bloquear / permitir) y acciones para **programar horarios** de acceso y **renombrarlo** en el router |
| **Internet** | Conectividad, IP pública, IPv6, modo WAN, DNS, *conectado desde* |
| **Fibra (ONT)** | Enlace óptico, potencia RX/TX (dBm), temperatura, tensión y corriente del transceptor, contadores de tramas |
| **Sistema** | Último arranque, carga de CPU, uso de memoria, nº de dispositivos (total / WiFi / cable), nivel de firewall |
| **Puertos** | Estado de LAN1–LAN4 con velocidad y dúplex |
| **WiFi** | Canal 2,4/5 GHz, SSID, **switch WiFi** y **switch WiFi de invitados** |
| **Acceso remoto** | **Switch** para activar/desactivar el acceso remoto a la web del router (puerto como atributo) |
| **Teléfono** | Registro de la línea VoIP |
| **Acciones** | Botón **Reiniciar** |

Además: flujo de configuración desde la UI, reautenticación, reconfiguración, opciones
(intervalo de sondeo, alta automática de rastreadores) y diagnósticos con los secretos
redactados.

## Instalación

### HACS (repositorio personalizado)

1. HACS → ⋮ → *Repositorios personalizados* → `https://github.com/davidmc473/orange-livebox-es`,
   tipo *Integración*.
2. Instala **Orange Livebox (España)** y reinicia Home Assistant.

### Manual

Copia `custom_components/orange_livebox_es` en la carpeta `config/custom_components/` de
tu Home Assistant y reinicia.

## Configuración

### Descubrimiento automático

Home Assistant detecta el Livebox solo (por su nombre en la red y su MAC): aparecerá en
*Ajustes → Dispositivos y servicios* como **Descubierto: Livebox 6**. Pulsa *Añadir* e
introduce la contraseña de administración.

### Alta manual

*Ajustes → Dispositivos y servicios → Añadir integración → Orange Livebox (España)*

| Campo | Valor |
|-------|-------|
| Host | `192.168.1.1` |
| Usuario | `admin` (desde la LAN la web siempre usa este usuario) |
| Contraseña | La de administración del router (por defecto, la clave WiFi de la etiqueta) |

> ⚠️ El router bloquea el acceso durante 1 minuto tras **3 contraseñas erróneas**.
> La integración nunca reintenta con una contraseña rechazada en el alta. Ojo: el router
> responde «contraseña incorrecta» también cuando otra sesión está activa; si te pasa,
> cierra la web del router y vuelve a intentarlo.

### Gestionar los dispositivos de la red

- **Quitar el acceso a Internet**: apaga el switch *Acceso a Internet* del dispositivo
  (equivale a «Siempre bloqueado» en la web del router). Encenderlo lo vuelve a permitir y
  elimina cualquier horario.
- **Horario de acceso** (control parental), acción `orange_livebox_es.set_access_schedule`:

  ```yaml
  action: orange_livebox_es.set_access_schedule
  target:
    entity_id: device_tracker.tablet_ninos
  data:
    monday: "8-14,16-21"   # horas permitidas (fin exclusivo)
    saturday: "10-22"
    sunday: "-"            # bloqueado todo el día
  # los días que no indiques quedan permitidos todo el día
  ```

- **Renombrar** en el router, acción `orange_livebox_es.set_device_name`.

El router admite como máximo 16 reglas de control parental.

### Convivencia con la web del router

El router **solo admite una sesión de administración a la vez**: si entras en su web,
Home Assistant queda fuera. En ese caso la integración **cede la sesión** durante el
*tiempo de cesión* (10 min por defecto): no vuelve a entrar para no echarte, y sus sensores
aparecen como *no disponibles* mientras tanto. Pasado ese tiempo vuelve a entrar (si sigues
en la web, en ese momento te pedirá iniciar sesión de nuevo).

Los switches y el botón de reinicio siguen funcionando durante la cesión: usarlos recupera
la sesión para Home Assistant.

### Opciones

- **Intervalo de sondeo**: 30 s por defecto (10–3600 s).
- **Activar automáticamente los rastreadores nuevos**: si lo desactivas, los clientes
  nuevos se crean deshabilitados (salvo que su MAC ya pertenezca a otro dispositivo de HA).
- **Tiempo de cesión de la sesión**: minutos que HA deja de entrar al router cuando detecta
  que estás usando su web (1–60, por defecto 10).

Solo se crean rastreadores para clientes **vistos conectados** desde que existe la
integración: el router guarda un histórico grande (MAC aleatorias de móviles, equipos
antiguos) que no tiene sentido importar.

## Cómo funciona

El Livebox 6 no tiene API pública. La web carga sus datos desde `cgi/cgi_*.js` y cifra
los formularios con AES-256-CBC usando una clave incrustada en cada página. La
integración replica ese protocolo sin ejecutar JavaScript. Los detalles están en
[`specs/001-livebox6-arcadyan/contracts/arcadyan-http.md`](specs/001-livebox6-arcadyan/contracts/arcadyan-http.md).

## Desarrollo (SDD)

El proyecto sigue *Spec-Driven Development*:

```
.specify/memory/constitution.md       principios del proyecto
specs/001-livebox6-arcadyan/   integración base (lectura, WiFi, reinicio)
specs/002-acceso-remoto/       switch de acceso remoto, entidades activas
specs/003-convivencia-sesion/  sesión única del router: ceder la sesión
specs/004-gestion-dispositivos/ acceso a Internet, horarios y nombre de los clientes
specs/005-descubrimiento/      descubrimiento automático (DHCP/ARP)
  spec.md        qué y por qué (historias, requisitos)
  research.md    hallazgos de la ingeniería inversa
  plan.md        diseño técnico y catálogo de entidades
  data-model.md  modelos normalizados
  contracts/     protocolo HTTP del router
  tasks.md       tareas y su estado
```

Estructura del código:

```
custom_components/orange_livebox_es/
  api/                 cliente del router, SIN dependencias de Home Assistant
    arcadyan/          driver del Livebox 6 (cliente + parser)
    jsparse.py         parser de los CGI JavaScript
    crypto.py          cifrado de formularios
  *.py                 plataformas de Home Assistant
```

### Tests

```bash
pip install -r requirements_test.txt
pytest                               # capa api/ (funciona también en Windows)
pip install pytest-homeassistant-custom-component
pytest                               # tests de la integración (Linux/WSL/Docker)
pytest -p no:homeassistant           # tests de protocolo (el arnés de HA bloquea sockets)
```

Prueba en vivo de solo lectura contra un router real:

```bash
LIVEBOX_PASSWORD=... python scripts/live_probe.py --devices
```

### Añadir otro router Orange

1. Captura `login.htm` y los CGI del modelo (`scripts/live_probe.py --dump capturas/`)
   y crea fixtures **anonimizadas**.
2. Si es otra web Arcadyan: ajusta `api/arcadyan/`. Si es otra familia: crea
   `api/<driver>/` con una subclase de `LiveboxClient` y regístrala en `api/__init__.py`.
3. Escribe una spec nueva en `specs/NNN-…/`.

## Licencia

MIT

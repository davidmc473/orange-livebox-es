"""Prueba en vivo (SOLO LECTURA) del cliente contra un router real.

Uso::

    LIVEBOX_PASSWORD=... python scripts/live_probe.py [--host 192.168.1.1] [--user admin]
                                                      [--dump DIR] [--devices]

``--dump DIR`` guarda los CGI en bruto (¡contienen secretos! no los subas a git).
No ejecuta ninguna acción de escritura.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = ROOT / "custom_components" / "orange_livebox_es"

# Importa la capa api/ sin cargar la parte de Home Assistant
sys.path.insert(0, str(ROOT))
for name, path in (
    ("custom_components", ROOT / "custom_components"),
    ("custom_components.orange_livebox_es", PKG_DIR),
):
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)

import aiohttp  # noqa: E402

from custom_components.orange_livebox_es.api import (  # noqa: E402
    async_create_client,
)
from custom_components.orange_livebox_es.api.arcadyan.client import POLL_CGIS  # noqa: E402
from custom_components.orange_livebox_es.api.redact import mask_number  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("LIVEBOX_HOST", "192.168.1.1"))
    parser.add_argument("--user", default=os.environ.get("LIVEBOX_USER", "admin"))
    parser.add_argument("--dump", type=Path)
    parser.add_argument("--devices", action="store_true", help="lista los clientes online")
    args = parser.parse_args()
    password = os.environ.get("LIVEBOX_PASSWORD")
    if not password:
        print("Define LIVEBOX_PASSWORD", file=sys.stderr)
        return 2

    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        client = await async_create_client(session, args.host, args.user, password)
        print(f"Driver: {client.driver}")
        t0 = time.perf_counter()
        await client.async_login()
        print(f"Login OK en {time.perf_counter() - t0:.2f}s")

        t0 = time.perf_counter()
        data = await client.async_get_data()
        print(f"Ciclo de lectura en {time.perf_counter() - t0:.2f}s")

        d = data.device
        print(f"\nEquipo: {d.manufacturer} {d.model} ({d.model_id}) FW {d.firmware_version}")
        print(f"        HW {d.hardware_version} · boot {d.bootloader_version} · ISP {d.isp}")
        s = data.system
        print(f"Sistema: uptime {s.uptime}s · CPU {s.cpu_load}% · memoria {s.memory_usage}%")
        w = data.wan
        print(
            f"WAN: conectado={w.connected} modo={w.mode} ipv4={'sí' if w.ipv4 else 'no'} "
            f"ipv6={'sí' if w.ipv6 else 'no'} uptime={w.uptime}s dns={len(w.dns_servers)}"
        )
        if (o := data.optical) is not None:
            print(
                f"Óptica: link={o.link_up} RX={o.rx_power} dBm TX={o.tx_power} dBm "
                f"T={o.temperature}°C V={o.voltage} bias={o.bias_current} mA "
                f"frames rx/tx={o.unicast_rx_frames}/{o.unicast_tx_frames}"
            )
        print(
            "Puertos:",
            ", ".join(
                f"{p.name}={'up' if p.link_up else 'down'}/{p.speed_mbps}" for p in data.lan_ports
            ),
        )
        if (wf := data.wifi) is not None:
            print(
                f"WiFi: activa={wf.enabled} (2.4={wf.enabled_24g}, 5={wf.enabled_5g}) "
                f"canales {wf.channel_24g}/{wf.channel_5g} · programación={wf.schedule_enabled} "
                f"· invitados={wf.guest_enabled}"
            )
        for line in data.voip_lines:
            print(f"VoIP: {mask_number(line.number)} registrada={line.registered}")
        if data.remote_access:
            print(f"Acceso remoto: {data.remote_access.enabled} puerto {data.remote_access.port}")
        print(f"Firewall: {data.firewall_level}")
        online = data.connected_devices
        print(
            f"Clientes: {len(data.devices)} conocidos, {len(online)} online "
            f"({sum(1 for c in online if c.connection.is_wifi)} WiFi)"
        )
        if args.devices:
            for dev in sorted(online, key=lambda x: x.ip or ""):
                print(
                    f"  {dev.ip or '-':15} {dev.connection.value:12} "
                    f"{(dev.signal_strength or ''):>4} {(dev.link_rate_mbps or ''):>5} "
                    f"{dev.name or '?'}"
                )

        if args.dump:
            args.dump.mkdir(parents=True, exist_ok=True)
            docs = await client.async_fetch_cgis(POLL_CGIS)
            for name, doc in docs.items():
                (args.dump / f"{name}.json").write_text(
                    json.dumps(
                        {"vars": doc.vars, "cfg": {k: v.value for k, v in doc.cfg.items()}},
                        indent=1,
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            print(f"\nCGI volcados en {args.dump} (contienen secretos)")

        await client.async_logout()
        print("\nLogout OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

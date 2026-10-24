"""Acceso a routers Orange España. Sin dependencias de Home Assistant (constitución IV).

Para añadir un modelo nuevo: crear ``api/<driver>/`` con una subclase de
:class:`LiveboxClient`, una función de detección y registrarlos en ``DRIVERS``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re

import aiohttp

from .arcadyan import ArcadyanLiveboxClient, is_arcadyan_login_page
from .base import Feature, LiveboxClient
from .exceptions import (
    CannotConnect,
    InvalidAuth,
    LiveboxError,
    LoginLocked,
    ParseError,
    SessionConflict,
    SessionExpired,
    UnsupportedRouter,
)
from .models import (
    AccessMode,
    AccessRule,
    ConnectedDevice,
    ConnectionType,
    DeviceInfo,
    LanPort,
    OpticalStatus,
    RemoteAccess,
    RouterData,
    SystemStatus,
    VoipLine,
    WanStatus,
    WifiStatus,
)

ClientFactory = Callable[[aiohttp.ClientSession, str, str, str], LiveboxClient]
Detector = Callable[[str, "str | None"], bool]

#: driver → (detector sobre login.htm, fábrica del cliente)
DRIVERS: dict[str, tuple[Detector, ClientFactory]] = {
    ArcadyanLiveboxClient.driver: (is_arcadyan_login_page, ArcadyanLiveboxClient),
}

_LOGIN_PATHS = ("login.htm",)


def create_client(
    driver: str, session: aiohttp.ClientSession, host: str, username: str, password: str
) -> LiveboxClient:
    """Instancia el cliente de un driver conocido."""
    try:
        _, factory = DRIVERS[driver]
    except KeyError as err:
        raise UnsupportedRouter(f"Driver desconocido: {driver}") from err
    return factory(session, host, username, password)


@dataclass(frozen=True, slots=True)
class RouterProbe:
    """Resultado de sondear un equipo sin credenciales (spec 005)."""

    driver: str
    #: la web es de un Livebox de Orange (no solo un router del mismo fabricante)
    is_livebox: bool
    #: modelo reconocido en la página de login, p. ej. «Livebox 6»
    model: str | None


_LIVEBOX_MODEL_RE = re.compile(r"livebox[_ -]?(\d+|fibra|\+)?", re.IGNORECASE)


def _livebox_model(html: str) -> str | None:
    """Modelo según la página de login; se prefiere el numerado (``Livebox_6.png``)."""
    suffixes = [m.group(1) or "" for m in _LIVEBOX_MODEL_RE.finditer(html)]
    if not suffixes:
        return None
    suffix = next((s for s in suffixes if s.isdigit()), None) or next(
        (s for s in suffixes if s), ""
    )
    if not suffix:
        return "Livebox"
    return f"Livebox {suffix.capitalize() if suffix.isalpha() else suffix}"


async def async_probe_router(session: aiohttp.ClientSession, host: str) -> RouterProbe:
    """Identifica el driver y si es un Livebox consultando la página de login."""
    base = host if "://" in host else f"http://{host}"
    base = base.rstrip("/")
    for path in _LOGIN_PATHS:
        try:
            async with session.get(
                f"{base}/{path}",
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.text(errors="replace")
                server = resp.headers.get("Server")
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CannotConnect(f"No se puede contactar con {base}: {err}") from err
        for driver, (detector, _) in DRIVERS.items():
            if detector(body, server):
                model = _livebox_model(body)
                return RouterProbe(driver=driver, is_livebox=model is not None, model=model)
    raise UnsupportedRouter(f"{base} no es un router Orange soportado")


async def async_detect_driver(session: aiohttp.ClientSession, host: str) -> str:
    """Identifica el driver adecuado consultando la página de login del router."""
    return (await async_probe_router(session, host)).driver


async def async_create_client(
    session: aiohttp.ClientSession, host: str, username: str, password: str
) -> LiveboxClient:
    """Detecta el modelo y devuelve un cliente sin autenticar."""
    driver = await async_detect_driver(session, host)
    return create_client(driver, session, host, username, password)


__all__ = [
    "DRIVERS",
    "AccessMode",
    "AccessRule",
    "CannotConnect",
    "ConnectedDevice",
    "ConnectionType",
    "DeviceInfo",
    "Feature",
    "InvalidAuth",
    "LanPort",
    "LiveboxClient",
    "LiveboxError",
    "LoginLocked",
    "OpticalStatus",
    "ParseError",
    "RemoteAccess",
    "RouterData",
    "RouterProbe",
    "SessionConflict",
    "SessionExpired",
    "SystemStatus",
    "UnsupportedRouter",
    "VoipLine",
    "WanStatus",
    "WifiStatus",
    "async_create_client",
    "async_detect_driver",
    "async_probe_router",
    "create_client",
]

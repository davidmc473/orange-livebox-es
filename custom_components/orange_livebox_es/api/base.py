"""Interfaz común de los drivers de router."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum

from .models import RouterData


class Feature(StrEnum):
    """Capacidades opcionales que puede ofrecer un driver."""

    REBOOT = "reboot"
    WIFI_SWITCH = "wifi_switch"
    GUEST_WIFI_SWITCH = "guest_wifi_switch"
    REMOTE_ACCESS_SWITCH = "remote_access_switch"
    DEVICE_ACCESS = "device_access"
    DEVICE_RENAME = "device_rename"


class LiveboxClient(ABC):
    """Cliente de un router Orange. Cada familia de firmware implementa uno."""

    #: identificador del driver (se guarda en la entrada de configuración)
    driver: str
    #: capacidades de escritura soportadas
    features: frozenset[Feature] = frozenset()

    def __init__(self, host: str, username: str, password: str) -> None:
        self.host = host
        self.username = username
        self.password = password

    @abstractmethod
    async def async_login(self) -> None:
        """Autentica contra el router. Lanza InvalidAuth / LoginLocked / CannotConnect."""

    @abstractmethod
    async def async_get_data(self) -> RouterData:
        """Lee y normaliza todo el estado del router."""

    async def async_logout(self) -> None:  # noqa: B027 - opcional: no todos los drivers tienen sesión
        """Cierra la sesión (best effort)."""

    async def async_reboot(self) -> None:
        raise NotImplementedError

    async def async_set_wifi_enabled(self, enabled: bool) -> None:
        raise NotImplementedError

    async def async_set_guest_wifi_enabled(self, enabled: bool) -> None:
        raise NotImplementedError

    async def async_set_remote_access_enabled(self, enabled: bool) -> None:
        raise NotImplementedError

    async def async_set_device_access(self, mac: str, schedule: list[str] | None) -> None:
        """Horario de acceso a Internet de un cliente (7 hex, lunes … domingo).

        ``None`` = permitido siempre (se elimina la regla).
        """
        raise NotImplementedError

    async def async_set_device_name(self, mac: str, name: str) -> None:
        raise NotImplementedError

"""Coordinador de sondeo del router."""

from __future__ import annotations

from datetime import timedelta
import logging
import math
import time
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    InvalidAuth,
    LiveboxClient,
    LiveboxError,
    LoginLocked,
    RouterData,
    SessionConflict,
)
from .const import CONF_SESSION_YIELD, DEFAULT_SCAN_INTERVAL, DEFAULT_SESSION_YIELD, DOMAIN

if TYPE_CHECKING:
    from .clients import TrackedClients

_LOGGER = logging.getLogger(__name__)

type LiveboxConfigEntry = ConfigEntry[LiveboxDataUpdateCoordinator]


class LiveboxDataUpdateCoordinator(DataUpdateCoordinator[RouterData]):
    """Lee el estado completo del router en cada ciclo.

    El router solo admite una sesión de administración (spec 003): si otra sesión (la
    web) expulsa a HA, el coordinador *cede* la sesión durante un tiempo configurable en
    vez de volver a entrar enseguida y expulsar al usuario.
    """

    config_entry: LiveboxConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: LiveboxConfigEntry, client: LiveboxClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.yield_seconds = 60 * entry.options.get(CONF_SESSION_YIELD, DEFAULT_SESSION_YIELD)
        self._yield_until: float | None = None
        #: clientes gestionados (se asigna en ``async_setup_entry``)
        self.clients: TrackedClients

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    @property
    def yielding(self) -> bool:
        return self._yield_until is not None and self._now() < self._yield_until

    @callback
    def async_end_yield(self) -> None:
        """Una orden explícita del usuario ha recuperado la sesión."""
        self._yield_until = None

    def _minutes_left(self) -> str:
        assert self._yield_until is not None
        return str(max(1, math.ceil((self._yield_until - self._now()) / 60)))

    async def _async_update_data(self) -> RouterData:
        if self.yielding:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="session_yielded",
                translation_placeholders={"minutes": self._minutes_left()},
            )
        self._yield_until = None
        try:
            return await self.client.async_get_data()
        except SessionConflict as err:
            self._yield_until = self._now() + self.yield_seconds
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="session_in_use",
                translation_placeholders={"minutes": self._minutes_left()},
            ) from err
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except LoginLocked as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="login_locked",
                translation_placeholders={"seconds": str(err.seconds)},
            ) from err
        except LiveboxError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

"""Constantes de la integración Orange Livebox (España)."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "orange_livebox_es"

CONF_DRIVER: Final = "driver"
CONF_TRACK_NEW_DEVICES: Final = "track_new_devices"
CONF_SESSION_YIELD: Final = "session_yield_minutes"

DEFAULT_HOST: Final = "192.168.1.1"
DEFAULT_USERNAME: Final = "admin"
DEFAULT_DRIVER: Final = "arcadyan"
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 3600
DEFAULT_TRACK_NEW_DEVICES: Final = True
#: minutos que HA deja de entrar al router si otra sesión (la web) lo está usando (spec 003)
DEFAULT_SESSION_YIELD: Final = 10
MIN_SESSION_YIELD: Final = 1
MAX_SESSION_YIELD: Final = 60

#: tiempo durante el que un switch mantiene el estado pedido mientras el router lo aplica
ASSUMED_STATE_SECONDS: Final = 60

PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
    Platform.SWITCH,
]

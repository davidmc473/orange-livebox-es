"""Acciones de la integración sobre los clientes del router (spec 004)."""

from __future__ import annotations

from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, service
import voluptuous as vol

from .api.schedule import DAYS
from .const import DOMAIN

SERVICE_SET_DEVICE_NAME = "set_device_name"
SERVICE_SET_ACCESS_SCHEDULE = "set_access_schedule"


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Registra las acciones; se aplican a los ``device_tracker`` de la integración."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SET_DEVICE_NAME,
        entity_domain=DEVICE_TRACKER_DOMAIN,
        schema={vol.Required("name"): cv.string},
        func="async_set_router_name",
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SET_ACCESS_SCHEDULE,
        entity_domain=DEVICE_TRACKER_DOMAIN,
        schema={vol.Optional(day): cv.string for day in DAYS},
        func="async_set_access_schedule",
    )

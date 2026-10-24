"""Flujo de configuración (US1, US8) y descubrimiento DHCP (spec 005)."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
import voluptuous as vol

from .api import (
    CannotConnect,
    InvalidAuth,
    LoginLocked,
    ParseError,
    RouterData,
    UnsupportedRouter,
    async_detect_driver,
    async_probe_router,
    create_client,
)
from .const import (
    CONF_DRIVER,
    CONF_SESSION_YIELD,
    CONF_TRACK_NEW_DEVICES,
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SESSION_YIELD,
    DEFAULT_TRACK_NEW_DEVICES,
    DEFAULT_USERNAME,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MAX_SESSION_YIELD,
    MIN_SCAN_INTERVAL,
    MIN_SESSION_YIELD,
)
from .coordinator import LiveboxConfigEntry
from .session import async_get_session

_LOGGER = logging.getLogger(__name__)

_PASSWORD_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)


def _user_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, DEFAULT_HOST)): str,
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, DEFAULT_USERNAME)): str,
            vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
        }
    )


async def async_validate_input(
    hass: HomeAssistant, host: str, username: str, password: str
) -> tuple[str, RouterData]:
    """Detecta el driver, hace login y una lectura completa. Devuelve (driver, datos)."""
    session = async_get_session(hass)
    driver = await async_detect_driver(session, host)
    client = create_client(driver, session, host, username, password)
    await client.async_login()
    data = await client.async_get_data()
    await client.async_logout()
    return driver, data


async def _async_try_validate(
    hass: HomeAssistant, host: str, username: str, password: str, errors: dict[str, str]
) -> tuple[str, RouterData] | None:
    try:
        return await async_validate_input(hass, host, username, password)
    except InvalidAuth:
        errors["base"] = "invalid_auth"
    except LoginLocked:
        errors["base"] = "login_locked"
    except CannotConnect:
        errors["base"] = "cannot_connect"
    except (UnsupportedRouter, ParseError):
        errors["base"] = "unsupported"
    except Exception:
        _LOGGER.exception("Error inesperado validando el router")
        errors["base"] = "unknown"
    return None


class LiveboxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Alta de un router."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_model: str | None = None

    async def _async_create_router_entry(
        self, host: str, user_input: Mapping[str, Any], driver: str, data: RouterData
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(data.device.serial_number, raise_on_progress=False)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        return self.async_create_entry(
            title=f"{data.device.model} ({data.device.serial_number})",
            data={
                CONF_HOST: host,
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_DRIVER: driver,
            },
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            result = await _async_try_validate(
                self.hass, host, user_input[CONF_USERNAME], user_input[CONF_PASSWORD], errors
            )
            if result is not None:
                return await self._async_create_router_entry(host, user_input, *result)
        return self.async_show_form(
            step_id="user", data_schema=_user_schema(user_input or {}), errors=errors
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """Spec 005: el vigilante de red de HA ha visto un equipo «livebox*» u OUI Arcadyan."""
        host = discovery_info.ip
        self._async_abort_entries_match({CONF_HOST: host})
        # Deduplica descubrimientos repetidos del mismo equipo (luego pasa a ser el nº serie)
        await self.async_set_unique_id(f"mac_{discovery_info.macaddress}")
        try:
            probe = await async_probe_router(async_get_session(self.hass), host)
        except (CannotConnect, UnsupportedRouter):
            return self.async_abort(reason="not_supported")
        if not probe.is_livebox:
            # p. ej. un router Arcadyan de otro operador: no se ofrece nada
            return self.async_abort(reason="not_supported")
        self._discovered_host = host
        self._discovered_model = probe.model or "Livebox"
        self.context["title_placeholders"] = {"name": f"{self._discovered_model} ({host})"}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovered_host is not None
        host = self._discovered_host
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await _async_try_validate(
                self.hass, host, user_input[CONF_USERNAME], user_input[CONF_PASSWORD], errors
            )
            if result is not None:
                return await self._async_create_router_entry(host, user_input, *result)
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                    vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
                }
            ),
            description_placeholders={"host": host, "model": self._discovered_model or ""},
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            result = await _async_try_validate(
                self.hass,
                entry.data[CONF_HOST],
                entry.data[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                errors,
            )
            if result is not None:
                _, data = result
                await self.async_set_unique_id(data.device.serial_number)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR}),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            result = await _async_try_validate(
                self.hass, host, user_input[CONF_USERNAME], user_input[CONF_PASSWORD], errors
            )
            if result is not None:
                driver, data = result
                await self.async_set_unique_id(data.device.serial_number)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_HOST: host,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_DRIVER: driver,
                    },
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema(user_input or entry.data),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: LiveboxConfigEntry) -> OptionsFlow:
        return LiveboxOptionsFlow()


class LiveboxOptionsFlow(OptionsFlow):
    """Opciones: sondeo, alta automática de rastreadores y cesión de sesión."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            user_input[CONF_SESSION_YIELD] = int(user_input[CONF_SESSION_YIELD])
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_TRACK_NEW_DEVICES,
                    default=options.get(CONF_TRACK_NEW_DEVICES, DEFAULT_TRACK_NEW_DEVICES),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_SESSION_YIELD,
                    default=options.get(CONF_SESSION_YIELD, DEFAULT_SESSION_YIELD),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SESSION_YIELD,
                        max=MAX_SESSION_YIELD,
                        step=1,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

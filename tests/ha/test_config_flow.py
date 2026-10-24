"""Tests del flujo de configuración (T031, US1, US8)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.orange_livebox_es.api import (
    CannotConnect,
    InvalidAuth,
    LoginLocked,
    RouterData,
    RouterProbe,
    UnsupportedRouter,
)
from custom_components.orange_livebox_es.const import (
    CONF_DRIVER,
    CONF_SESSION_YIELD,
    CONF_TRACK_NEW_DEVICES,
    DOMAIN,
)

from .conftest import ENTRY_DATA, SERIAL

USER_INPUT = {CONF_HOST: "192.168.1.1", CONF_USERNAME: "admin", CONF_PASSWORD: "s3cret"}
VALIDATE = "custom_components.orange_livebox_es.config_flow.async_validate_input"


@pytest.fixture(autouse=True)
def no_setup():
    with patch("custom_components.orange_livebox_es.async_setup_entry", return_value=True):
        yield


async def test_user_flow(hass: HomeAssistant, router_data: RouterData) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(VALIDATE, AsyncMock(return_value=("arcadyan", router_data))):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Livebox 6 ({SERIAL})"
    assert result["data"] == {**USER_INPUT, CONF_DRIVER: "arcadyan"}
    assert result["result"].unique_id == SERIAL


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (InvalidAuth(), "invalid_auth"),
        (LoginLocked(60), "login_locked"),
        (CannotConnect(), "cannot_connect"),
        (UnsupportedRouter(), "unsupported"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors_then_recover(
    hass: HomeAssistant, router_data: RouterData, error: Exception, key: str
) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with patch(VALIDATE, AsyncMock(side_effect=error)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": key}

    with patch(VALIDATE, AsyncMock(return_value=("arcadyan", router_data))):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured(
    hass: HomeAssistant, router_data: RouterData, config_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with patch(VALIDATE, AsyncMock(return_value=("arcadyan", router_data))):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**USER_INPUT, CONF_HOST: "192.168.1.254"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == "192.168.1.254"


async def test_reauth(
    hass: HomeAssistant, router_data: RouterData, config_entry: MockConfigEntry
) -> None:
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch(VALIDATE, AsyncMock(side_effect=InvalidAuth())):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "mal"}
        )
    assert result["errors"] == {"base": "invalid_auth"}
    with patch(VALIDATE, AsyncMock(return_value=("arcadyan", router_data))) as validate:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "nueva"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_PASSWORD] == "nueva"
    validate.assert_awaited_once_with(hass, "192.168.1.1", "admin", "nueva")


async def test_reauth_wrong_device(
    hass: HomeAssistant, router_data: RouterData, config_entry: MockConfigEntry
) -> None:
    router_data.device.serial_number = "OTRO"
    result = await config_entry.start_reauth_flow(hass)
    with patch(VALIDATE, AsyncMock(return_value=("arcadyan", router_data))):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "x"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"


async def test_reconfigure(
    hass: HomeAssistant, router_data: RouterData, config_entry: MockConfigEntry
) -> None:
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    with patch(VALIDATE, AsyncMock(return_value=("arcadyan", router_data))):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**USER_INPUT, CONF_HOST: "livebox.home"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data == {**ENTRY_DATA, CONF_HOST: "livebox.home"}


async def test_options(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 60.0, CONF_TRACK_NEW_DEVICES: False, CONF_SESSION_YIELD: 15.0},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {
        CONF_SCAN_INTERVAL: 60,
        CONF_TRACK_NEW_DEVICES: False,
        CONF_SESSION_YIELD: 15,
    }


# --- Spec 005: descubrimiento DHCP ------------------------------------------------------

PROBE = "custom_components.orange_livebox_es.config_flow.async_probe_router"


def _dhcp(ip: str = "192.168.1.1"):
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

    return DhcpServiceInfo(ip=ip, hostname="livebox", macaddress="608d26c24f14")


async def test_dhcp_discovery(hass: HomeAssistant, router_data: RouterData) -> None:
    from homeassistant.config_entries import SOURCE_DHCP

    with patch(PROBE, AsyncMock(return_value=RouterProbe("arcadyan", True, "Livebox 6"))):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp()
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {"host": "192.168.1.1", "model": "Livebox 6"}
    flow = hass.config_entries.flow.async_get(result["flow_id"])
    assert flow["context"]["title_placeholders"] == {"name": "Livebox 6 (192.168.1.1)"}

    with patch(VALIDATE, AsyncMock(return_value=("arcadyan", router_data))) as validate:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "s3cret"}
        )
    validate.assert_awaited_once_with(hass, "192.168.1.1", "admin", "s3cret")
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SERIAL
    assert result["data"][CONF_HOST] == "192.168.1.1"


@pytest.mark.parametrize(
    "probe",
    [
        AsyncMock(return_value=RouterProbe("arcadyan", False, None)),
        AsyncMock(side_effect=UnsupportedRouter()),
        AsyncMock(side_effect=CannotConnect()),
    ],
)
async def test_dhcp_discovery_not_supported(hass: HomeAssistant, probe: AsyncMock) -> None:
    from homeassistant.config_entries import SOURCE_DHCP

    with patch(PROBE, probe):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp()
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_dhcp_discovery_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    from homeassistant.config_entries import SOURCE_DHCP

    probe = AsyncMock(return_value=RouterProbe("arcadyan", True, "Livebox 6"))
    with patch(PROBE, probe):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp()
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    probe.assert_not_awaited()  # ni siquiera se contacta con el router


async def test_dhcp_discovery_deduplicated(hass: HomeAssistant) -> None:
    from homeassistant.config_entries import SOURCE_DHCP

    with patch(PROBE, AsyncMock(return_value=RouterProbe("arcadyan", True, "Livebox 6"))):
        first = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp()
        )
        second = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp()
        )
    assert first["type"] is FlowResultType.FORM
    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "already_in_progress"

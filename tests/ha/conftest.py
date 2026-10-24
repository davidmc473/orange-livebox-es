"""Fixtures de Home Assistant: cliente simulado y entrada de configuración."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.orange_livebox_es.api import Feature, LiveboxClient, RouterData
from custom_components.orange_livebox_es.api.arcadyan.parser import build_router_data
from custom_components.orange_livebox_es.const import CONF_DRIVER, DOMAIN

from ..conftest import load_fixture_docs

SERIAL = "ARLT00TEST01"
ENTRY_DATA = {
    CONF_HOST: "192.168.1.1",
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "s3cret",
    CONF_DRIVER: "arcadyan",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> Iterator[None]:
    yield


class FakeClient(LiveboxClient):
    """Cliente en memoria que registra las órdenes recibidas."""

    driver = "arcadyan"
    features = frozenset(Feature)
    base_url = "http://192.168.1.1"

    def __init__(self, data: RouterData) -> None:
        super().__init__("192.168.1.1", "admin", "s3cret")
        self.data = data
        self.error: Exception | None = None
        self.calls: list[object] = []

    async def async_login(self) -> None:
        self.calls.append("login")

    async def async_get_data(self) -> RouterData:
        if self.error is not None:
            raise self.error
        return self.data

    async def async_logout(self) -> None:
        self.calls.append("logout")

    async def async_reboot(self) -> None:
        self.calls.append("reboot")

    async def async_set_wifi_enabled(self, enabled: bool) -> None:
        self.calls.append(("wifi", enabled))
        assert self.data.wifi is not None
        self.data.wifi.enabled_24g = self.data.wifi.enabled_5g = enabled

    async def async_set_guest_wifi_enabled(self, enabled: bool) -> None:
        self.calls.append(("guest_wifi", enabled))
        assert self.data.wifi is not None
        self.data.wifi.guest_enabled = enabled

    async def async_set_device_access(self, mac: str, schedule: list[str] | None) -> None:
        self.calls.append(("device_access", mac, schedule))

    async def async_set_device_name(self, mac: str, name: str) -> None:
        self.calls.append(("device_name", mac, name))

    async def async_set_remote_access_enabled(self, enabled: bool) -> None:
        self.calls.append(("remote_access", enabled))
        assert self.data.remote_access is not None
        self.data.remote_access.enabled = enabled


@pytest.fixture
def router_data() -> RouterData:
    return build_router_data(load_fixture_docs())


@pytest.fixture
def mock_client(router_data: RouterData) -> Iterator[FakeClient]:
    client = FakeClient(router_data)
    with patch("custom_components.orange_livebox_es.create_client", return_value=client):
        yield client


@pytest.fixture
def config_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL,
        title=f"Livebox 6 ({SERIAL})",
        data=dict(ENTRY_DATA),
    )
    entry.add_to_hass(hass)
    return entry

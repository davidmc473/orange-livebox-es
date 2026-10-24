"""Tests de protocolo contra el router falso (T024–T027)."""

from __future__ import annotations

import time

import aiohttp
import pytest

from custom_components.orange_livebox_es.api import (
    UnsupportedRouter,
    async_create_client,
    async_detect_driver,
    async_probe_router,
)
from custom_components.orange_livebox_es.api.arcadyan.client import ArcadyanLiveboxClient
from custom_components.orange_livebox_es.api.exceptions import (
    CannotConnect,
    InvalidAuth,
    LiveboxError,
    LoginLocked,
    SessionConflict,
)

pytestmark = pytest.mark.enable_socket


@pytest.fixture
async def session():
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as s:
        yield s


def _client(session, host, password="s3cret") -> ArcadyanLiveboxClient:
    return ArcadyanLiveboxClient(session, host, "admin", password)


async def test_detect_and_login(fake_router, session) -> None:
    state, host = fake_router
    assert await async_detect_driver(session, host) == "arcadyan"
    client = await async_create_client(session, host, "admin", "s3cret")
    await client.async_login()
    assert len(state.sessions) == 1


async def test_detect_unsupported(session) -> None:
    from aiohttp import web
    from aiohttp.test_utils import TestServer

    app = web.Application()

    async def other_router(request: web.Request) -> web.Response:
        return web.Response(text="<html>otro router</html>")

    app.router.add_get("/login.htm", other_router)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        with pytest.raises(UnsupportedRouter):
            await async_detect_driver(session, f"127.0.0.1:{server.port}")
    finally:
        await server.close()


async def test_cannot_connect(session) -> None:
    client = ArcadyanLiveboxClient(session, "127.0.0.1:1", "admin", "x", timeout=2)
    with pytest.raises(CannotConnect):
        await client.async_login()


async def test_invalid_auth_and_lockout(fake_router, session) -> None:
    state, host = fake_router
    client = _client(session, host, password="mal")
    with pytest.raises(InvalidAuth):
        await client.async_login()
    with pytest.raises(InvalidAuth):
        await client.async_login()
    # El tercer fallo activa el bloqueo del router: se detecta y se informa
    with pytest.raises(LoginLocked) as err:
        await client.async_login()
    assert err.value.seconds == 60
    # Con el router bloqueado no se envían credenciales
    posts = state.login_posts
    with pytest.raises(LoginLocked):
        await _client(session, host).async_login()
    assert state.login_posts == posts


async def test_get_data(fake_router, session) -> None:
    state, host = fake_router
    client = _client(session, host)
    data = await client.async_get_data()  # login implícito
    assert data.device.serial_number == "ARLT00TEST01"
    assert len(data.connected_devices) == 5
    assert data.wifi is not None and data.wifi.guest_enabled is False
    # una sola página para el token y luego los CGI
    pages = [r for r in state.requests if not r.startswith("GET cgi_")]
    assert pages == ["GET login.htm", "GET support_leds.htm"]


async def test_relogin_when_session_expires(fake_router, session) -> None:
    state, host = fake_router
    client = _client(session, host)
    await client.async_get_data()
    # caducidad por inactividad (> KICK_WINDOW desde la última petición correcta)
    client._last_ok = time.monotonic() - 9 * 60
    state.expire_sessions()
    data = await client.async_get_data()
    assert data.device.serial_number == "ARLT00TEST01"
    assert state.login_posts == 2


async def test_optional_cgi_missing_is_tolerated(fake_router, session) -> None:
    state, host = fake_router
    original = state.cgi
    state.cgi = lambda name: None if name == "infoFtth" else original(name)  # type: ignore[method-assign]
    data = await _client(session, host).async_get_data()
    assert data.optical is None


async def test_required_cgi_missing_fails(fake_router, session) -> None:
    state, host = fake_router
    original = state.cgi
    state.cgi = lambda name: None if name == "router_status" else original(name)  # type: ignore[method-assign]
    with pytest.raises(CannotConnect):
        await _client(session, host).async_get_data()


async def test_guest_wifi_on(fake_router, session) -> None:
    state, host = fake_router
    client = _client(session, host)
    await client.async_set_guest_wifi_enabled(True)
    assert state.applied == [
        {
            "referer": "wifi_guest.htm",
            "action": "ui_wireless",
            "action_params": None,
            "submit_button": "wifi_guest.htm",
            "changes": {"196669004000": "1", "196734004000": "1", "196798004000": "1"},
        }
    ]


async def test_guest_wifi_no_change_sends_nothing(fake_router, session) -> None:
    state, host = fake_router
    await _client(session, host).async_set_guest_wifi_enabled(False)
    assert state.applied == []


async def test_wifi_off(fake_router, session) -> None:
    state, host = fake_router
    await _client(session, host).async_set_wifi_enabled(False)
    assert len(state.applied) == 1
    applied = state.applied[0]
    assert applied["action"] == "ui_wireless"
    assert applied["referer"] == "wifi_main.htm"
    assert applied["changes"] == {
        "196637000000": "0",  # wl_enable24G
        "196701000000": "0",  # wl_enable5G
        "983267000000": "1",  # wl_enable_change
        "196626000000": "0",  # wifi_schedule_enable (la web la desactiva)
    }


async def test_remote_access_off(fake_router, session) -> None:
    state, host = fake_router
    await _client(session, host).async_set_remote_access_enabled(False)
    assert state.applied == [
        {
            "referer": "advanced_user_remote_access.htm",
            "action": "ui_management",
            "action_params": "remote_management_mod",
            "submit_button": "advanced_user_remote_access.htm",
            # solo rm_en: usuario, contraseña y puerto no viajan
            "changes": {"983248000000": "0"},
        }
    ]


async def test_remote_access_no_change_sends_nothing(fake_router, session) -> None:
    state, host = fake_router
    await _client(session, host).async_set_remote_access_enabled(True)
    assert state.applied == []


async def test_login_with_negative_remaining_time(fake_router, session) -> None:
    # Observado en el router real tras un login fallido: valor negativo = sin bloqueo
    state, host = fake_router
    state.lock_seconds = -302017
    await _client(session, host).async_login()
    assert len(state.sessions) == 1


async def test_reboot(fake_router, session) -> None:
    state, host = fake_router
    client = _client(session, host)
    await client.async_reboot()
    assert state.applied == [
        {
            "referer": "support_restart.htm",
            "action": "reboot",
            "action_params": "RebootFromGUI",
            "submit_button": "index.htm",
            "changes": {},
        }
    ]


async def test_reboot_refused_during_call(fake_router, session) -> None:
    state, host = fake_router
    state.overrides["have_phone_call"] = "var query_have_call_status='1';"
    with pytest.raises(LiveboxError):
        await _client(session, host).async_reboot()
    assert state.applied == []


async def test_logout(fake_router, session) -> None:
    state, host = fake_router
    client = _client(session, host)
    await client.async_login()
    assert len(state.sessions) == 1
    await client.async_logout()
    assert state.sessions == set()


# --- Spec 003: sesión única -------------------------------------------------------------


async def test_kicked_by_browser_yields_instead_of_relogin(fake_router, session) -> None:
    state, host = fake_router
    client = _client(session, host)
    await client.async_get_data()
    state.login_other_client()  # el usuario entra en la web
    with pytest.raises(SessionConflict):
        await client.async_get_data()
    assert state.login_posts == 1  # no se ha vuelto a entrar (no expulsa al usuario)


async def test_same_user_agent_sessions_coexist(fake_router, session) -> None:
    _, host = fake_router
    first, second = _client(session, host), _client(session, host)
    await first.async_get_data()
    await second.async_get_data()
    assert (await first.async_get_data()).device.serial_number == "ARLT00TEST01"


async def test_rejected_login_after_success_is_conflict(fake_router, session) -> None:
    state, host = fake_router
    client = _client(session, host)
    await client.async_get_data()
    client._last_ok = time.monotonic() - 9 * 60
    state.expire_sessions()
    state.reject_next_logins = 1
    with pytest.raises(SessionConflict):
        await client.async_get_data()
    # y en cuanto el router acepta de nuevo, todo vuelve a funcionar
    assert (await client.async_get_data()).device.serial_number == "ARLT00TEST01"


async def test_first_login_rejection_is_invalid_auth(fake_router, session) -> None:
    state, host = fake_router
    state.reject_next_logins = 1
    with pytest.raises(InvalidAuth):
        await _client(session, host).async_get_data()


async def test_persistent_rejections_escalate_to_invalid_auth(fake_router, session) -> None:
    state, host = fake_router
    client = _client(session, host)
    await client.async_get_data()
    hour_ago = time.monotonic() - 3700
    client._rejections = [hour_ago, hour_ago + 600]
    client._sid = None
    state.reject_next_logins = 1
    with pytest.raises(InvalidAuth):
        await client.async_get_data()


async def test_command_relogins_when_kicked(fake_router, session) -> None:
    state, host = fake_router
    client = _client(session, host)
    await client.async_get_data()
    state.login_other_client()
    await client.async_set_guest_wifi_enabled(True)  # orden explícita: recupera la sesión
    assert len(state.applied) == 1
    assert state.applied[0]["changes"]["196669004000"] == "1"


async def test_command_kicked_mid_apply_retries_once(fake_router, session) -> None:
    state, host = fake_router
    client = _client(session, host)
    await client.async_get_data()
    state.kick_before_apply = True  # expulsión entre leer la página y enviar la orden
    await client.async_set_remote_access_enabled(False)
    assert len(state.applied) == 1
    assert state.applied[0]["changes"] == {"983248000000": "0"}
    assert state.login_posts == 2


async def test_reboot_connection_drop_is_success(fake_router, session) -> None:
    state, host = fake_router
    state.drop_after_apply = True
    await _client(session, host).async_reboot()
    assert [a["action"] for a in state.applied] == ["reboot"]


async def test_consecutive_commands_wait_for_router(fake_router, session) -> None:
    """FR-307: la segunda orden espera a que el router asiente la primera."""
    state, host = fake_router
    state.busy_seconds = 0.5
    client = _client(session, host)
    client.settle_seconds = {"ui_wireless": 0.6}
    await client.async_set_guest_wifi_enabled(True)
    state.overrides["wlan_guest"] = (
        state.cgi("wlan_guest")
        .replace('"ssid_enable24G3", "196669004000", "0"', '"ssid_enable24G3", "196669004000", "1"')
        .replace('"ssid_enable5G3", "196734004000", "0"', '"ssid_enable5G3", "196734004000", "1"')
    )
    await client.async_set_guest_wifi_enabled(False)
    assert [a["changes"]["196669004000"] for a in state.applied] == ["1", "0"]
    assert state.dropped_busy == 0


async def test_busy_router_command_is_retried(fake_router, session) -> None:
    """FR-308: corte con la sesión válida → un reintento tras esperar."""
    state, host = fake_router
    state.busy_seconds = 0.3
    client = _client(session, host)
    client.settle_seconds = {"ui_management": 0}
    client.busy_retry_delay = 0.4
    await client.async_set_remote_access_enabled(False)
    state.overrides["remote_management_osp"] = state.cgi("remote_management_osp").replace(
        '"rm_en", "983248000000", "1"', '"rm_en", "983248000000", "0"'
    )
    await client.async_set_remote_access_enabled(True)
    assert state.dropped_busy == 1
    assert [a["changes"] for a in state.applied] == [
        {"983248000000": "0"},
        {"983248000000": "1"},
    ]


# --- Spec 004: gestión de dispositivos ---------------------------------------------------


async def test_block_device_uses_first_free_slot(fake_router, session) -> None:
    state, host = fake_router
    await _client(session, host).async_set_device_access("02:00:00:00:00:01", ["000000"] * 7)
    assert len(state.applied) == 1
    applied = state.applied[0]
    assert applied["referer"] == "network_access_schedule.htm"
    assert applied["action"] == "ui_parentalcontrol"
    assert applied["action_params"] == "mac_filter_mod"
    assert applied["submit_button"] == "network_connected.htm"
    # hueco 2 (0 y 1 ocupados); macFilter_active ya era 1 → no viaja
    assert applied["changes"] == {
        "655381003000": "1",  # macFilter_enable_2
        "655382003000": "02:00:00:00:00:01",  # macFilter_mac_2
        **{f"6553{83 + d}003000": "000000" for d in range(7)},
    }


async def test_schedule_existing_rule_updates_its_slot(fake_router, session) -> None:
    state, host = fake_router
    schedule = ["00FF00"] * 7
    await _client(session, host).async_set_device_access("02:00:00:00:00:03", schedule)
    # hueco 0 ya existía (bloqueado): solo cambian los días
    assert state.applied[0]["changes"] == {f"6553{83 + d}001000": "00FF00" for d in range(7)}


async def test_allow_device_removes_rule(fake_router, session) -> None:
    state, host = fake_router
    await _client(session, host).async_set_device_access("02:00:00:00:00:05", None)
    assert state.applied[0]["changes"] == {
        "655381002000": "0",
        "655382002000": "",
        **{f"6553{83 + d}002000": "" for d in range(7)},
    }


async def test_allow_device_without_rule_is_noop(fake_router, session) -> None:
    state, host = fake_router
    await _client(session, host).async_set_device_access("02:00:00:00:00:01", None)
    assert state.applied == []


async def test_block_device_without_free_slots(fake_router, session) -> None:
    state, host = fake_router
    full = state.cgi("firewall_mac_filter")
    for n in range(2, 16):
        full = full.replace(
            f'"macFilter_mac_{n}", "655382{n + 1:03d}000", ""',
            f'"macFilter_mac_{n}", "655382{n + 1:03d}000", "02:00:00:00:01:{n:02d}"',
        )
    state.overrides["firewall_mac_filter"] = full
    with pytest.raises(LiveboxError, match="huecos"):
        await _client(session, host).async_set_device_access("02:00:00:00:00:01", ["000000"] * 7)


async def test_rename_existing_custom_name(fake_router, session) -> None:
    state, host = fake_router
    await _client(session, host).async_set_device_name("02:00:00:00:00:05", "Bombilla salón")
    applied = state.applied[0]
    assert applied["referer"] == "network_customize.htm"
    assert applied["action"] == "ui_add_pclist"
    assert applied["action_params"] == '"02:00:00:00:00:05,Bombilla salón"'
    assert applied["changes"] == {"983253001000": "Bombilla salón"}  # client_hostname0


async def test_rename_new_device_takes_free_slot(fake_router, session) -> None:
    state, host = fake_router
    await _client(session, host).async_set_device_name("02:00:00:00:00:02", "Móvil")
    assert state.applied[0]["changes"] == {
        "983253003000": "Móvil",  # client_hostname2 (primer hueco libre)
        "983254003000": "02:00:00:00:00:02",  # client_mac2
        "983255003000": "desktop",  # client_deviceType2: valor por defecto de la web
    }


@pytest.mark.parametrize("bad", ["", "  ", "a/b", "it's", 'x"y', "a&b", "a$b", "a`b", r"a\b"])
async def test_rename_rejects_invalid_names(fake_router, session, bad: str) -> None:
    state, host = fake_router
    with pytest.raises(LiveboxError):
        await _client(session, host).async_set_device_name("02:00:00:00:00:02", bad)
    assert state.applied == []


# --- Spec 005: descubrimiento -----------------------------------------------------------


async def test_probe_router_livebox(fake_router, session) -> None:
    _, host = fake_router
    probe = await async_probe_router(session, host)
    assert probe.driver == "arcadyan"
    assert probe.is_livebox is True
    assert probe.model == "Livebox 6"


async def test_probe_other_arcadyan_router_is_not_livebox(session) -> None:
    from aiohttp import web
    from aiohttp.test_utils import TestServer

    async def other_isp(request: web.Request) -> web.Response:
        return web.Response(
            text='<script src="js/arc-crypt.js"></script><script>a="login.cgi"</script>Station',
            headers={"Server": "Arcadyan httpd 1.0"},
        )

    app = web.Application()
    app.router.add_get("/login.htm", other_isp)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        probe = await async_probe_router(session, f"127.0.0.1:{server.port}")
    finally:
        await server.close()
    assert probe.driver == "arcadyan"
    assert probe.is_livebox is False
    assert probe.model is None

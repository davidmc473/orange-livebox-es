"""Cliente HTTP para la web Arcadyan del Livebox 6 de Orange España.

Protocolo documentado en ``specs/001-livebox6-arcadyan/contracts/arcadyan-http.md``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from ..base import Feature, LiveboxClient
from ..crypto import PageMaterial, extract_page_material, login_field
from ..exceptions import (
    CannotConnect,
    InvalidAuth,
    LiveboxError,
    LoginLocked,
    ParseError,
    SessionConflict,
    SessionExpired,
)
from ..jsparse import JsDocument, parse_js
from ..models import RouterData
from .parser import build_router_data, mac_filter_days, mac_filter_slots, normalize_mac

_LOGGER = logging.getLogger(__name__)

DRIVER = "arcadyan"
DEFAULT_TIMEOUT = 15

#: página ligera usada para obtener el token de cada ciclo de lectura
TOKEN_PAGE = "support_leds.htm"

#: CGI leídos en cada ciclo (FR-003)
POLL_CGIS: tuple[str, ...] = (
    "router_status",
    "info",
    "infoInternet",
    "infoFtth",
    "infoLan",
    "clients",
    "wlan_combine",
    "wlan_guest",
    "network_connected",
    "remote_management_osp",
    "firewall_main",
    "firewall_mac_filter",
)

#: CGI imprescindibles: si fallan, el ciclo falla
REQUIRED_CGIS = frozenset({"router_status", "info"})

#: si la sesión se pierde antes de esto desde la última petición correcta, nos expulsaron
#: (la web caduca por inactividad a los 10 min: ``szLoginTimeout``)
KICK_WINDOW = 8 * 60
#: rechazos de login tras un éxito previo: a partir de aquí se asume clave cambiada
CONFLICT_ESCALATION_ATTEMPTS = 3
CONFLICT_ESCALATION_SECONDS = 3600

#: segundos que el router necesita tras cada orden (``wait`` de subForm en la web, FR-307)
SETTLE_SECONDS: dict[str, float] = {
    "ui_wireless": 20,
    "ui_management": 5,
    "ui_parentalcontrol": 5,
    "ui_add_pclist": 5,
}
#: caracteres que la web no admite en el nombre de un dispositivo
INVALID_NAME_CHARS = "'\"\\/&`$"
DEFAULT_SETTLE_SECONDS = 5.0
#: espera antes del único reintento de una orden cortada con la sesión válida (FR-308)
BUSY_RETRY_DELAY = 10.0

_GUI_CHECK_FIELD = "805443298771"
_GUI_CHECK_RE = re.compile(r'addCfg\("gui_cehck_token",\s*"\d+",\s*"(\d+)"\)')
_GUI_CHECK_FIELD_RE = re.compile(
    r"name='(\d+)' value='\"\+do_encode\(getCfg\(\"gui_cehck_token\"\)\)"
)
# Puede ser negativo (sin bloqueo); solo un valor > 0 indica bloqueo activo
_REMAINING_RE = re.compile(r"var\s+remaining_time\s*=\s*parseInt\('(-?\d+)'\)")
_HAVE_CALL_RE = re.compile(r"query_have_call_status\s*=\s*['\"]?(\d)")


def is_arcadyan_login_page(html: str, server_header: str | None) -> bool:
    """Heurística de detección del driver (FR-008)."""
    return bool(
        (server_header and "arcadyan" in server_header.lower())
        or ("arc-crypt.js" in html and "login.cgi" in html)
    )


class ArcadyanLiveboxClient(LiveboxClient):
    """Driver para routers Orange ES con web Arcadyan (Livebox 6 / Livebox+)."""

    driver = DRIVER
    #: ajustables en tests
    settle_seconds = SETTLE_SECONDS
    busy_retry_delay = BUSY_RETRY_DELAY
    features = frozenset(
        {
            Feature.REBOOT,
            Feature.WIFI_SWITCH,
            Feature.GUEST_WIFI_SWITCH,
            Feature.REMOTE_ACCESS_SWITCH,
            Feature.DEVICE_ACCESS,
            Feature.DEVICE_RENAME,
        }
    )

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        super().__init__(host, username, password)
        self._session = session
        self._base = _base_url(host)
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._sid: str | None = None
        self._lock = asyncio.Lock()
        # Spec 003: distinguir expulsión / caducidad / contraseña errónea
        self._last_ok: float | None = None
        self._login_ok_once = False
        self._rejections: list[float] = []
        # FR-307: el router no acepta otra orden hasta que se asienta la anterior
        self._busy_until = 0.0

    # --- HTTP de bajo nivel -----------------------------------------------------------
    def _headers(self, referer: str | None = None) -> dict[str, str]:
        headers = {"User-Agent": "Mozilla/5.0 (HomeAssistant orange_livebox_es)"}
        if self._sid:
            headers["Cookie"] = f"SID={self._sid}"
        if referer:
            headers["Referer"] = f"{self._base}/{referer.lstrip('/')}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        referer: str | None = None,
        data: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> tuple[int, str, str, aiohttp.ClientResponse]:
        url = f"{self._base}/{path.lstrip('/')}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(referer),
                data=data,
                params=params,
                allow_redirects=False,
                timeout=self._timeout,
            ) as resp:
                body = await resp.text(encoding="utf-8", errors="replace")
                location = resp.headers.get("Location", "")
                if (
                    self._sid
                    and resp.status < 400
                    and not self._is_login_redirect(resp.status, location)
                ):
                    self._last_ok = time.monotonic()
                return resp.status, location, body, resp
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CannotConnect(f"Error de conexión con {url}: {err}") from err

    @staticmethod
    def _is_login_redirect(status: int, location: str) -> bool:
        return status in (301, 302, 303, 307) and "login" in location.lower()

    async def _get_page(self, page: str) -> tuple[str, PageMaterial]:
        status, location, body, _ = await self._request("GET", page)
        if self._is_login_redirect(status, location):
            raise SessionExpired(page)
        if status != 200:
            raise CannotConnect(f"{page}: HTTP {status}")
        return body, extract_page_material(body)

    async def _get_cgi(self, name: str, material: PageMaterial, referer: str) -> JsDocument:
        now = str(int(time.time() * 1000))
        status, location, body, _ = await self._request(
            "GET",
            f"cgi/cgi_{name}.js",
            referer=referer,
            params={"_tn": material.token, "_t": now, "_": now},
        )
        if self._is_login_redirect(status, location):
            raise SessionExpired(name)
        if status != 200:
            raise CannotConnect(f"cgi_{name}.js: HTTP {status}")
        return parse_js(body)

    # --- sesión -----------------------------------------------------------------------
    async def async_login(self) -> None:
        async with self._lock:
            await self._login()

    async def _login(self) -> None:
        self._sid = None
        status, _, body, resp = await self._request("GET", "login.htm")
        if status != 200:
            raise CannotConnect(f"login.htm: HTTP {status}")
        if not is_arcadyan_login_page(body, resp.headers.get("Server")):
            raise ParseError("login.htm no corresponde a una web Arcadyan")
        remaining = _REMAINING_RE.search(body)
        if remaining and int(remaining.group(1)) > 0:
            raise LoginLocked(int(remaining.group(1)))
        material = extract_page_material(body)

        status, location, _, resp = await self._request(
            "POST",
            "login.cgi",
            referer="login.htm",
            data={
                "httoken": material.token,
                "cnlvd2xh": login_field(self.password, material),
                "dfr597hf": login_field(self.username, material),
            },
        )
        cookie = resp.cookies.get("SID")
        if status in (301, 302, 303) and "login" not in location.lower() and cookie:
            self._sid = cookie.value
            self._last_ok = time.monotonic()
            self._login_ok_once = True
            self._rejections.clear()
            _LOGGER.debug("Login correcto en %s", self._base)
            return
        if "login" in location.lower():
            # Puede ser contraseña errónea, bloqueo recién activado u otra sesión activa
            status, _, body, _ = await self._request("GET", "login.htm")
            remaining = _REMAINING_RE.search(body) if status == 200 else None
            if remaining and int(remaining.group(1)) > 0:
                raise LoginLocked(int(remaining.group(1)))
            raise self._rejection_error()
        raise CannotConnect(f"Respuesta inesperada del login: HTTP {status} {location!r}")

    def _rejection_error(self) -> LiveboxError:
        """Login rechazado: el router usa el mismo error para clave errónea y sesión ocupada.

        Si estas credenciales ya funcionaron, se asume conflicto de sesión salvo que los
        rechazos persistan (≥ 3 a lo largo de más de una hora): entonces la clave cambió.
        """
        if not self._login_ok_once:
            return InvalidAuth("El router ha rechazado las credenciales")
        now = time.monotonic()
        self._rejections.append(now)
        if (
            len(self._rejections) >= CONFLICT_ESCALATION_ATTEMPTS
            and now - self._rejections[0] >= CONFLICT_ESCALATION_SECONDS
        ):
            return InvalidAuth("El router rechaza las credenciales de forma persistente")
        return SessionConflict(
            "El router ha rechazado el login: probablemente hay otra sesión de "
            "administración activa (¿está abierta la web del router?)"
        )

    async def async_logout(self) -> None:
        if not self._sid:
            return
        async with self._lock:
            try:
                _, material = await self._get_page(TOKEN_PAGE)
                await self._request(
                    "POST", "logout.cgi", referer=TOKEN_PAGE, data={"httoken": material.token}
                )
            except LiveboxError as err:
                _LOGGER.debug("Logout fallido (ignorado): %s", err)
            finally:
                self._sid = None

    async def _with_session(self, func, *args, force: bool = False):
        """Ejecuta ``func`` con sesión válida.

        Si la sesión se pierde poco después de haberla usado, otra sesión nos ha expulsado:
        en lecturas (``force=False``) se lanza ``SessionConflict`` para ceder la sesión; en
        órdenes explícitas (``force=True``) se vuelve a entrar y se reintenta una vez.
        Si llevaba tiempo sin usarse, es caducidad normal y se reabre.
        """
        if not self._sid:
            await self._login()
        try:
            return await func(*args)
        except SessionExpired as err:
            kicked = self._last_ok is not None and time.monotonic() - self._last_ok < KICK_WINDOW
            self._sid = None
            if kicked and not force:
                raise SessionConflict(
                    "Otra sesión de administración ha expulsado a Home Assistant"
                ) from err
            _LOGGER.debug(
                "Sesión perdida (%s), repitiendo login", "expulsión" if kicked else "caducada"
            )
            await self._login()
            return await func(*args)

    # --- lectura ----------------------------------------------------------------------
    async def async_fetch_cgis(
        self, names: Iterable[str], page: str = TOKEN_PAGE
    ) -> dict[str, JsDocument]:
        """Lee CGI arbitrarios (útil para diagnosticar otros modelos)."""
        async with self._lock:
            return await self._with_session(self._fetch_cgis, tuple(names), page)

    async def _fetch_cgis(self, names: tuple[str, ...], page: str) -> dict[str, JsDocument]:
        _, material = await self._get_page(page)
        docs: dict[str, JsDocument] = {}
        for name in names:
            try:
                docs[name] = await self._get_cgi(name, material, page)
            except CannotConnect as err:
                if name in REQUIRED_CGIS:
                    raise
                _LOGGER.debug("CGI opcional %s no disponible: %s", name, err)
        return docs

    async def async_get_data(self) -> RouterData:
        docs = await self.async_fetch_cgis(POLL_CGIS)
        return build_router_data(docs)

    # --- escritura --------------------------------------------------------------------
    async def _get_gui_check(self) -> tuple[str, str]:
        """(nombre del campo, valor) del *check token* de la GUI.

        El router lo **rota tras cada orden** (observado en vivo): se lee de ``global.js``
        justo antes de cada envío, como hace la web al cargar cada página. Con un valor
        caducado el router corta la conexión sin aplicar nada.
        """
        status, _, body, _ = await self._request("GET", "js/global.js")
        match = _GUI_CHECK_RE.search(body) if status == 200 else None
        if match is None:
            raise LiveboxError("No se encuentra el token de control en js/global.js")
        field = _GUI_CHECK_FIELD_RE.search(body)
        return (field.group(1) if field else _GUI_CHECK_FIELD), match.group(1)

    async def _apply(
        self,
        page: str,
        action: str,
        changes: Mapping[str, str] | None = None,
        *,
        action_params: str | None = None,
        submit_button: str | None = None,
        material: PageMaterial | None = None,
    ) -> None:
        """POST a ``apply_abstract.cgi`` como ``subForm()`` de la web (FR-007).

        ``changes`` es {id numérico de addCfg: valor nuevo}.
        """
        if (delay := self._busy_until - time.monotonic()) > 0:
            _LOGGER.debug("Esperando %.0f s a que el router aplique la orden anterior", delay)
            await asyncio.sleep(delay)
        if material is None:
            _, material = await self._get_page(page)
        form: dict[str, str] = {
            "action": material.encode(action),
            "httoken": material.token,
            "submit_button": submit_button or page,
        }
        if action_params:
            form["action_params"] = material.encode(action_params)
        check_field, check_value = await self._get_gui_check()
        form[check_field] = material.encode(check_value)
        for cfg_id, value in (changes or {}).items():
            form[cfg_id] = material.encode(value)

        try:
            status, location, body, _ = await self._request(
                "POST", "apply_abstract.cgi", referer=page, data=form
            )
        except CannotConnect:
            # Con una sesión expulsada el router corta la conexión en vez de redirigir
            await self._get_page(TOKEN_PAGE)  # lanza SessionExpired si es el caso
            raise
        if self._is_login_redirect(status, location):
            raise SessionExpired("apply_abstract.cgi")
        if status not in (200, 302, 303):
            raise LiveboxError(f"apply_abstract.cgi: HTTP {status}")
        self._busy_until = time.monotonic() + self.settle_seconds.get(
            action, DEFAULT_SETTLE_SECONDS
        )
        _LOGGER.debug("apply %s → HTTP %s %s %s", action, status, location, body[:200])

    async def _retry_busy(self, func, *args):
        """FR-308: un corte con la sesión válida suele ser el router aún ocupado.

        Se reintenta una vez; ``func`` recalcula los cambios, así que si la orden llegó a
        aplicarse no se reenvía.
        """
        try:
            return await func(*args)
        except CannotConnect as err:
            _LOGGER.debug(
                "El router no aceptó la orden (%s); reintento en %.0f s", err, self.busy_retry_delay
            )
            await asyncio.sleep(self.busy_retry_delay)
            return await func(*args)

    async def _page_cfg(self, page: str, cgi: str) -> tuple[PageMaterial, JsDocument]:
        """Material de la página origen + CGI con los ids/valores actuales."""
        _, material = await self._get_page(page)
        return material, await self._get_cgi(cgi, material, page)

    async def async_reboot(self) -> None:
        async with self._lock:
            await self._with_session(self._reboot, force=True)

    async def _reboot(self) -> None:
        page = "support_restart.htm"
        _, material = await self._get_page(page)
        # La web no reinicia si hay una llamada en curso
        now = str(int(time.time() * 1000))
        status, _, body, _ = await self._request(
            "GET",
            "cgi/cgi_have_phone_call.js",
            referer=page,
            params={"_tn": material.token, "_t": now, "_": now},
        )
        if status == 200 and (match := _HAVE_CALL_RE.search(body)) and match.group(1) == "1":
            raise LiveboxError("Hay una llamada telefónica en curso; reinicio cancelado")
        try:
            await self._apply(
                page,
                "reboot",
                action_params="RebootFromGUI",
                submit_button="index.htm",
                material=material,
            )
        except CannotConnect as err:
            # La sesión seguía viva: el corte es el propio reinicio (no se reintenta)
            _LOGGER.debug("Conexión cortada tras ordenar el reinicio: %s", err)
        self._sid = None

    async def async_set_wifi_enabled(self, enabled: bool) -> None:
        async with self._lock:
            await self._with_session(self._retry_busy, self._set_wifi_enabled, enabled, force=True)

    async def _set_wifi_enabled(self, enabled: bool) -> None:
        value = "1" if enabled else "0"
        page = "wifi_main.htm"
        material, doc = await self._page_cfg(page, "wlan_combine")
        changes = changed_cfg(doc, {"wl_enable24G": value, "wl_enable5G": value})
        if not changes:
            return
        # Igual que el botón de la web: marca el cambio y desactiva la programación WiFi
        changes.update(changed_cfg(doc, {"wl_enable_change": "1", "wifi_schedule_enable": "0"}))
        await self._apply(page, "ui_wireless", changes, material=material)

    async def async_set_guest_wifi_enabled(self, enabled: bool) -> None:
        async with self._lock:
            await self._with_session(
                self._retry_busy, self._set_guest_wifi_enabled, enabled, force=True
            )

    async def _set_guest_wifi_enabled(self, enabled: bool) -> None:
        value = "1" if enabled else "0"
        page = "wifi_guest.htm"
        material, doc = await self._page_cfg(page, "wlan_guest")
        # Solo cuentan las bandas reales; 5G_H (sin radio en este modelo) se envía como
        # hace la web, pero no justifica por sí sola una escritura
        if not changed_cfg(doc, {"ssid_enable24G3": value, "ssid_enable5G3": value}):
            return
        changes = changed_cfg(
            doc, {"ssid_enable24G3": value, "ssid_enable5G3": value, "ssid_enable5G_H3": value}
        )
        await self._apply(page, "ui_wireless", changes, material=material)

    async def async_set_remote_access_enabled(self, enabled: bool) -> None:
        async with self._lock:
            await self._with_session(
                self._retry_busy, self._set_remote_access_enabled, enabled, force=True
            )

    async def _set_remote_access_enabled(self, enabled: bool) -> None:
        page = "advanced_user_remote_access.htm"
        material, doc = await self._page_cfg(page, "remote_management_osp")
        # La web reenvía usuario/contraseña/puerto, pero al no cambiar no viajan (genForm)
        changes = changed_cfg(doc, {"rm_en": "1" if enabled else "0"})
        if changes:
            await self._apply(
                page,
                "ui_management",
                changes,
                action_params="remote_management_mod",
                material=material,
            )

    async def async_set_device_access(self, mac: str, schedule: list[str] | None) -> None:
        async with self._lock:
            await self._with_session(
                self._retry_busy, self._set_device_access, mac, schedule, force=True
            )

    async def _set_device_access(self, mac: str, schedule: list[str] | None) -> None:
        """Programación de acceso (spec 004): igual que ``save()`` de la web."""
        target = normalize_mac(mac)
        if target is None:
            raise LiveboxError(f"MAC no válida: {mac!r}")
        page = "network_access_schedule.htm"
        material, doc = await self._page_cfg(page, "firewall_mac_filter")
        slots = mac_filter_slots(doc)
        days = mac_filter_days(doc)
        slot = next(
            (n for n in slots if normalize_mac(doc.cfg_value(f"macFilter_mac_{n}")) == target),
            None,
        )
        if schedule is None:
            if slot is None:
                return  # ya está permitido siempre
            wanted = {
                f"macFilter_enable_{slot}": "0",
                f"macFilter_mac_{slot}": "",
                **{f"macFilter_sch_{slot}_{day}": "" for day in range(days)},
            }
        else:
            if len(schedule) != days:
                raise LiveboxError(f"El horario debe tener {days} días")
            if slot is None:
                slot = next((n for n in slots if not doc.cfg_value(f"macFilter_mac_{n}")), None)
                if slot is None:
                    raise LiveboxError(
                        f"No quedan huecos libres en el control parental ({len(slots)} reglas)"
                    )
            wanted = {
                "macFilter_active": "1",
                f"macFilter_enable_{slot}": "1",
                f"macFilter_mac_{slot}": target,
                **{f"macFilter_sch_{slot}_{day}": schedule[day].upper() for day in range(days)},
            }
        changes = changed_cfg(doc, wanted)
        if changes:
            await self._apply(
                page,
                "ui_parentalcontrol",
                changes,
                action_params="mac_filter_mod",
                submit_button="network_connected.htm",
                material=material,
            )

    async def async_set_device_name(self, mac: str, name: str) -> None:
        name = name.strip()
        if not name or any(char in INVALID_NAME_CHARS for char in name):
            raise LiveboxError(
                f"Nombre no válido; no puede estar vacío ni contener {INVALID_NAME_CHARS}"
            )
        async with self._lock:
            await self._with_session(self._retry_busy, self._set_device_name, mac, name, force=True)

    async def _set_device_name(self, mac: str, name: str) -> None:
        """Personalizar dispositivo (spec 004): igual que ``save()`` de la web."""
        target = normalize_mac(mac)
        if target is None:
            raise LiveboxError(f"MAC no válida: {mac!r}")
        page = "network_customize.htm"
        material, doc = await self._page_cfg(page, "clients")
        slots = sorted(
            int(key.removeprefix("client_mac"))
            for key in doc.cfg
            if key.startswith("client_mac") and key.removeprefix("client_mac").isdigit()
        )
        slot = next(
            (n for n in slots if normalize_mac(doc.cfg_value(f"client_mac{n}")) == target), None
        )
        if slot is None:
            slot = next((n for n in slots if not doc.cfg_value(f"client_mac{n}")), None)
            if slot is None:
                raise LiveboxError("No quedan huecos libres para nombres personalizados")
            device_type = "desktop"  # valor por defecto de la web
        else:
            device_type = doc.cfg_value(f"client_deviceType{slot}") or "desktop"
        changes = changed_cfg(
            doc,
            {
                f"client_hostname{slot}": name,
                f"client_mac{slot}": target,
                f"client_deviceType{slot}": device_type,
            },
        )
        if changes:
            await self._apply(
                page,
                "ui_add_pclist",
                changes,
                action_params=f'"{target},{name}"',
                submit_button="network_connected.htm",
                material=material,
            )

    # --- utilidades -------------------------------------------------------------------
    @property
    def base_url(self) -> str:
        return self._base

    def debug_state(self) -> dict[str, Any]:
        return {"base_url": self._base, "logged_in": self._sid is not None}


def changed_cfg(doc: JsDocument, wanted: Mapping[str, str]) -> dict[str, str]:
    """{id: valor} de las entradas que cambian (``genForm`` solo envía lo modificado).

    Las entradas que el CGI no declara se omiten: la web tampoco las enviaría.
    """
    changes: dict[str, str] = {}
    for name, value in wanted.items():
        entry = doc.cfg.get(name)
        if entry is not None and entry.value != value:
            changes[entry.id] = value
    return changes


def _base_url(host: str) -> str:
    host = host.strip().rstrip("/")
    if "://" not in host:
        host = f"http://{host}"
    parts = urlsplit(host)
    return f"{parts.scheme}://{parts.netloc}"

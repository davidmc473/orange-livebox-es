"""Router Arcadyan falso para tests de protocolo.

Reproduce el comportamiento observado en el Livebox 6 real (contracts/arcadyan-http.md):
material criptográfico por página, login cifrado, cookie SID, Referer obligatorio en los
CGI (si falta → 404), bloqueo tras 3 fallos y ``apply_abstract.cgi`` cifrado.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import secrets
import string
import time
from typing import Any

from aiohttp import web

from custom_components.orange_livebox_es.api.crypto import PageMaterial, aes_decode

FIXTURES = Path(__file__).parent / "fixtures" / "arcadyan"
GIF_PREFIX = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
GUI_CHECK_TOKEN = "2031700051"
SERVER = "Arcadyan httpd 1.0"
PAGES = {
    "index.htm",
    "support_leds.htm",
    "support_information.htm",
    "support_restart.htm",
    "wifi_main.htm",
    "wifi_guest.htm",
    "advanced_user_remote_access.htm",
    "network_access_schedule.htm",
    "network_customize.htm",
}


def _rand(n: int) -> str:
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(n))


def _md5_b64(value: str) -> str:
    return hashlib.md5(base64.b64encode(value.encode()), usedforsecurity=False).hexdigest()


@dataclass
class FakeRouterState:
    username: str = "admin"
    password: str = "s3cret"
    lock_seconds: int = 0
    failed_logins: int = 0
    sessions: set[str] = field(default_factory=set)
    materials: dict[str, PageMaterial] = field(default_factory=dict)
    applied: list[dict[str, Any]] = field(default_factory=list)
    requests: list[str] = field(default_factory=list)
    login_posts: int = 0
    overrides: dict[str, str] = field(default_factory=dict)
    #: spec 003 — sesión única: User-Agent de cada sesión
    session_ua: dict[str, str] = field(default_factory=dict)
    #: rechaza los próximos N logins aunque la clave sea correcta (router ocupado)
    reject_next_logins: int = 0
    #: otro cliente inicia sesión justo antes del próximo apply (expulsión en mitad)
    kick_before_apply: bool = False
    #: corta la conexión tras registrar el próximo apply (p. ej. el reinicio)
    drop_after_apply: bool = False
    #: tras una orden, el router está ocupado estos segundos y corta las siguientes (FR-307)
    busy_seconds: float = 0.0
    #: token de control de la GUI: el router real lo rota tras cada orden
    gui_check_token: str = GUI_CHECK_TOKEN
    busy_until: float = 0.0
    dropped_busy: int = 0

    def new_material(self) -> PageMaterial:
        material = PageMaterial(key=_rand(32), iv=_rand(16), token=str(secrets.randbelow(10**10)))
        self.materials[material.token] = material
        return material

    def expire_sessions(self) -> None:
        self.sessions.clear()

    def login_other_client(self, user_agent: str = "Mozilla/5.0 Chrome/130") -> None:
        """Un navegador inicia sesión: expulsa a las sesiones con otro User-Agent."""
        for sid, ua in list(self.session_ua.items()):
            if ua != user_agent:
                self.sessions.discard(sid)
                del self.session_ua[sid]

    def cgi(self, name: str) -> str | None:
        if name in self.overrides:
            return self.overrides[name]
        path = FIXTURES / f"cgi_{name}.js"
        return path.read_text(encoding="utf-8") if path.exists() else None


def _page_html(material: PageMaterial, extra: str = "") -> str:
    payload = base64.b64encode((material.key + material.iv + material.token).encode()).decode()
    return (
        "<!DOCTYPE html><html><head>"
        '<script type="text/javascript" src="js/arc-crypt.js"></script>'
        f"<script>{extra}</script></head><body>"
        '<div id="header-logo-livebox" style="background-image:url(images/Livebox_6.png)"></div>'
        '<form name="tF2" action="/cgi-bin/login.exe"></form>'
        '<script>document.tF2.action="login.cgi";</script>'
        f'<img title=spacer src="{GIF_PREFIX}{payload}" border=0></body></html>'
    )


def _decode_login_field(value: str, material: PageMaterial) -> str:
    plain = aes_decode(value, material.key, material.iv)
    decoded = base64.b64decode(plain).decode()
    _, digest = decoded.split(" ", 1)
    return digest


def build_app(state: FakeRouterState) -> web.Application:
    app = web.Application()

    def _authed(request: web.Request) -> bool:
        return request.cookies.get("SID") in state.sessions

    def _redirect(location: str, **kwargs: Any) -> web.Response:
        return web.Response(status=302, headers={"Location": location, "Server": SERVER}, **kwargs)

    async def login_page(request: web.Request) -> web.Response:
        state.requests.append("GET login.htm")
        material = state.new_material()
        extra = f"var remaining_time=parseInt('{state.lock_seconds}');"
        return web.Response(
            text=_page_html(material, extra), content_type="text/html", headers={"Server": SERVER}
        )

    async def login_cgi(request: web.Request) -> web.Response:
        state.login_posts += 1
        form = await request.post()
        material = state.materials.get(str(form.get("httoken")))
        if state.lock_seconds > 0 or material is None:
            return _redirect("/login.htm?err=1")
        if state.reject_next_logins > 0:
            state.reject_next_logins -= 1
            return _redirect("/login.htm?err=1")
        user_ok = _decode_login_field(str(form["dfr597hf"]), material) == _md5_b64(state.username)
        pwd_ok = _decode_login_field(str(form["cnlvd2xh"]), material) == _md5_b64(state.password)
        if not (user_ok and pwd_ok):
            state.failed_logins += 1
            if state.failed_logins >= 3:
                state.lock_seconds = 60
            return _redirect("/login.htm?err=1")
        state.failed_logins = 0
        sid = "".join(secrets.choice(string.digits) for _ in range(64))
        user_agent = request.headers.get("User-Agent", "")
        state.login_other_client(user_agent)  # sesión única por cliente (spec 003)
        state.sessions.add(sid)
        state.session_ua[sid] = user_agent
        resp = _redirect("/index.htm")
        resp.headers["Set-Cookie"] = f"SID={sid}; PATH=/; HttpOnly;"
        return resp

    async def page(request: web.Request) -> web.Response:
        name = request.match_info["page"]
        state.requests.append(f"GET {name}")
        if name not in PAGES:
            return web.Response(status=404)
        if not _authed(request):
            return _redirect("/login.htm")
        return web.Response(text=_page_html(state.new_material()), content_type="text/html")

    async def cgi(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        state.requests.append(f"GET cgi_{name}")
        if not _authed(request):
            return _redirect("/login.htm")
        if "Referer" not in request.headers:
            return web.Response(status=404)
        if request.query.get("_tn") not in state.materials:
            return web.Response(status=404)
        body = state.cgi(name)
        if body is None:
            return web.Response(status=404)
        return web.Response(text=body, content_type="application/x-javascript")

    def _drop(request: web.Request) -> web.Response:
        # El router real corta la conexión sin responder
        if request.transport is not None:
            request.transport.close()
        return web.Response(status=500)

    async def apply(request: web.Request) -> web.Response:
        if state.kick_before_apply:
            state.kick_before_apply = False
            state.login_other_client()
        if not _authed(request):
            # Con sesión expulsada el router real corta la conexión (Server disconnected)
            await request.read()
            return _drop(request)
        if "Referer" not in request.headers:
            return web.Response(status=404)
        form = await request.post()
        if time.monotonic() < state.busy_until:
            state.dropped_busy += 1
            return _drop(request)
        material = state.materials.get(str(form.get("httoken")))
        if material is None:
            return web.Response(status=403)
        decoded = {k: aes_decode(str(v), material.key, material.iv) for k, v in form.items()}
        if decoded.pop("805443298771", None) != state.gui_check_token:
            # token caducado: el router real corta la conexión sin aplicar nada
            return _drop(request)
        decoded.pop("httoken")
        state.applied.append(
            {
                "referer": request.headers["Referer"].rsplit("/", 1)[-1],
                "action": decoded.pop("action"),
                "action_params": decoded.pop("action_params", None),
                "submit_button": str(form.get("submit_button")),
                "changes": {k: v for k, v in decoded.items() if k != "submit_button"},
            }
        )
        state.busy_until = time.monotonic() + state.busy_seconds
        state.gui_check_token = str(secrets.randbelow(9 * 10**9) + 10**9)
        if state.drop_after_apply:
            state.drop_after_apply = False
            return _drop(request)
        return web.Response(text="<html>ok</html>", content_type="text/html")

    async def logout(request: web.Request) -> web.Response:
        state.sessions.discard(request.cookies.get("SID", ""))
        return web.Response(text="")

    async def global_js(request: web.Request) -> web.Response:
        # Mismo formato que el global.js real (frmHead)
        body = (
            "function frmHead(na,_option){\n"
            f'addCfg("gui_cehck_token", "983272000000", "{state.gui_check_token}");\n'
            "OUTF+=\"<INPUT type='hidden' name='805443298771' value='\""
            '+do_encode(getCfg("gui_cehck_token"))+"\'>\\n";}\n'
        )
        return web.Response(text=body, content_type="application/x-javascript")

    app.router.add_get("/login.htm", login_page)
    app.router.add_post("/login.cgi", login_cgi)
    app.router.add_post("/logout.cgi", logout)
    app.router.add_post("/apply_abstract.cgi", apply)
    app.router.add_get("/js/global.js", global_js)
    app.router.add_get("/cgi/cgi_{name}.js", cgi)
    app.router.add_get("/{page}", page)
    return app

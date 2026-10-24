"""Configuración común de tests.

Si Home Assistant no está instalado (p. ej. en Windows), se registra un paquete
``custom_components.orange_livebox_es`` vacío para poder importar la capa ``api/`` sin
ejecutar el ``__init__`` de la integración; los tests de HA se saltan solos.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "arcadyan"
sys.path.insert(0, str(ROOT))

try:
    import homeassistant  # noqa: F401

    HAS_HA = True
except ImportError:
    HAS_HA = False
    for _name, _path in (
        ("custom_components", ROOT / "custom_components"),
        ("custom_components.orange_livebox_es", ROOT / "custom_components" / "orange_livebox_es"),
    ):
        _module = types.ModuleType(_name)
        _module.__path__ = [str(_path)]
        sys.modules.setdefault(_name, _module)


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    """Reparte los tests según el arnés disponible.

    - ``tests/ha`` necesita el plugin de Home Assistant.
    - ``test_client.py`` levanta un router falso en 127.0.0.1 y el plugin de HA bloquea
      los sockets, así que se ejecuta aparte: ``pytest -p no:homeassistant``.
    """
    ha_plugin = config.pluginmanager.has_plugin("homeassistant")
    if collection_path.name == "ha" and collection_path.is_dir() and not ha_plugin:
        return True
    if collection_path.name == "test_client.py" and ha_plugin:
        return True
    return None


def load_fixture_docs() -> dict:
    """CGI de las fixtures ya parseados, por nombre."""
    from custom_components.orange_livebox_es.api.jsparse import parse_js

    return {
        path.stem.removeprefix("cgi_"): parse_js(path.read_text(encoding="utf-8"))
        for path in FIXTURES.glob("cgi_*.js")
    }


@pytest.fixture
def fixture_docs() -> dict:
    return load_fixture_docs()


@pytest.fixture
async def fake_router() -> AsyncIterator[tuple]:
    """Arranca el router falso; devuelve (estado, host:puerto)."""
    from aiohttp.test_utils import TestServer

    from .fake_router import FakeRouterState, build_app

    state = FakeRouterState()
    server = TestServer(build_app(state), host="127.0.0.1")
    await server.start_server()
    try:
        yield state, f"127.0.0.1:{server.port}"
    finally:
        await server.close()

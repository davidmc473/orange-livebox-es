"""Tests del cifrado de formularios (T022).

Los vectores se generaron ejecutando ``ArcAES`` y ``arc.crypt.md5`` del propio firmware
(``js/global.js`` y ``js/arc-crypt.js``) con Node.js.
"""

from __future__ import annotations

import base64
import hashlib

import pytest

from custom_components.orange_livebox_es.api.crypto import (
    PageMaterial,
    aes_decode,
    aes_encode,
    extract_page_material,
    login_field,
    random_token,
)
from custom_components.orange_livebox_es.api.exceptions import ParseError

KEY = "0123456789abcdefghijklmnopqrstuv"
IV = "ABCDEFGHIJKLMNOP"
VECTORS = {
    "0": "%87%07%27%82%28%a4%5e%ce%a2%1e%fe%c7%2f%88%c2%89",
    "1": "%88%7c%61%fb%01%49%e6%52%50%e6%5f%9b%61%53%ce%b0",
    "2031700051": "%14%cd%45%c0%53%41%bb%a2%12%dc%fc%d0%04%31%46%ab",
    "reboot": "%71%92%26%ac%1f%9a%eb%0a%1a%e7%54%1b%75%78%ae%58",
    "ui_wireless": "%1b%41%58%b6%dd%15%cd%a3%4c%be%1c%a9%29%9e%05%a0",
    "RebootFromGUI": "%e4%52%43%87%bf%3d%07%63%d8%80%bd%4f%ba%ff%ea%69",
    "exactly16bytes!!": "%f2%19%5c%34%44%a4%6b%4f%3d%a3%81%f7%0d%a2%de%49",
    "a longer value spanning several AES blocks 1234567890": (
        "%28%32%d7%e8%12%9f%59%9e%1f%a6%bd%c8%c2%0d%ae%ea%21%47%8f%bc%a3%82%6e%d5%16%93"
        "%09%8c%60%46%cc%b9%f7%e0%05%d4%e7%d6%41%12%d5%07%ec%5d%1d%97%db%1f%ba%fb%c7%1e"
        "%35%7d%aa%c5%2d%7e%2d%1c%38%54%29%a6"
    ),
}


@pytest.mark.parametrize(("plain", "expected"), VECTORS.items())
def test_aes_encode_matches_router_javascript(plain: str, expected: str) -> None:
    assert aes_encode(plain, KEY, IV) == expected
    assert aes_decode(expected, KEY, IV) == plain


def test_empty_value_is_not_encrypted() -> None:
    assert aes_encode("", KEY, IV) == ""


def test_md5_matches_router_javascript() -> None:
    # arc.crypt.md5.hex(btoa("admin"))
    assert hashlib.md5(b"YWRtaW4=").hexdigest() == "db69fc039dcbd2962cb4d28f5891aae1"


def test_extract_page_material() -> None:
    payload = base64.b64encode((KEY + IV + "1436609381").encode()).decode()
    html = (
        '<html><img src="images/x.png"><img title=spacer src="data:image/gif;base64,'
        f'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7{payload}" border=0></html>'
    )
    material = extract_page_material(html)
    assert material == PageMaterial(key=KEY, iv=IV, token="1436609381")


def test_extract_page_material_missing() -> None:
    with pytest.raises(ParseError):
        extract_page_material("<html>sin token</html>")


def test_login_field_roundtrip() -> None:
    material = PageMaterial(KEY, IV, "1")
    field = login_field("admin", material)
    decoded = base64.b64decode(aes_decode(field, KEY, IV)).decode()
    rand, digest = decoded.split(" ")
    assert len(rand) == 32 and rand.isalnum() and rand == rand.lower()
    assert digest == "db69fc039dcbd2962cb4d28f5891aae1"


def test_random_token_alphabet() -> None:
    token = random_token()
    assert len(token) == 32
    assert set(token) <= set("0123456789abcdefghijklmnopqrstuvwxyz")

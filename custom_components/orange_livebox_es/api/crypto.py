"""Cifrado de formularios de la web Arcadyan (ver contracts/arcadyan-http.md §1–3)."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import re
import secrets
import string

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .exceptions import ParseError

_SPACER_RE = re.compile(r"""src\s*=\s*["'](data:image/[^"']+)["']""", re.IGNORECASE)
# 22 caracteres de "data:image/gif;base64," + 56 del GIF 1x1 (ArcBase._t: substr(78))
_SPACER_PREFIX_LEN = 78
_RAND_ALPHABET = string.digits + string.ascii_lowercase


@dataclass(frozen=True, slots=True)
class PageMaterial:
    """Clave, IV y token anti-CSRF incrustados en cada página."""

    key: str
    iv: str
    token: str

    def encode(self, value: str) -> str:
        return aes_encode(value, self.key, self.iv)

    def decode(self, value: str) -> str:
        return aes_decode(value, self.key, self.iv)


def extract_page_material(html: str) -> PageMaterial:
    """Extrae el material criptográfico de la imagen espaciadora ``data:`` de la página."""
    for match in _SPACER_RE.finditer(html):
        src = match.group(1)
        if not src.startswith("data:"):
            continue
        payload = src[_SPACER_PREFIX_LEN:]
        payload = re.sub(r"[^A-Za-z0-9+/=]", "", payload)
        payload += "=" * (-len(payload) % 4)
        try:
            raw = base64.b64decode(payload).decode("latin-1")
        except (binascii.Error, ValueError):
            continue
        if len(raw) > 48:
            return PageMaterial(key=raw[:32], iv=raw[32:48], token=raw[48:])
    raise ParseError("La página no contiene el material de sesión (imagen data:)")


def _to_block(value: str, size: int | None = None) -> bytes:
    """``ArcAES.IntToByteArray``: un byte por carácter y relleno con ceros."""
    data = value.encode("latin-1", errors="replace")
    width = size if size is not None else -(-len(data) // 16) * 16
    return data[:width].ljust(width, b"\0")


def aes_encode(value: str, key: str, iv: str) -> str:
    """``do_encode`` de la web: AES-256-CBC, padding con ceros, salida ``%xx``."""
    if value == "":
        return ""
    cipher = Cipher(algorithms.AES(_to_block(key, 32)), modes.CBC(_to_block(iv, 16)))
    encryptor = cipher.encryptor()
    ct = encryptor.update(_to_block(value)) + encryptor.finalize()
    return "".join(f"%{b:02x}" for b in ct)


def aes_decode(value: str, key: str, iv: str) -> str:
    """``do_decode`` de la web (acepta ``%xx%xx`` o hex plano)."""
    hexstr = value.replace("%", "")
    try:
        ct = bytes.fromhex(hexstr)
    except ValueError:
        return value
    if not ct or len(ct) % 16:
        return value
    cipher = Cipher(algorithms.AES(_to_block(key, 32)), modes.CBC(_to_block(iv, 16)))
    decryptor = cipher.decryptor()
    pt = decryptor.update(ct) + decryptor.finalize()
    return pt.replace(b"\0", b"").decode("latin-1")


def _btoa(value: str) -> str:
    return base64.b64encode(value.encode("latin-1")).decode("ascii")


def random_token(length: int = 32) -> str:
    """``generatepassword()`` de login.htm."""
    return "".join(secrets.choice(_RAND_ALPHABET) for _ in range(length))


def login_field(value: str, material: PageMaterial) -> str:
    """Campo de login: ``do_encode(btoa(rand32 + " " + md5hex(btoa(valor))))``."""
    digest = hashlib.md5(_btoa(value).encode("ascii"), usedforsecurity=False).hexdigest()
    return material.encode(_btoa(f"{random_token()} {digest}"))

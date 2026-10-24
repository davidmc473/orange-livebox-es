"""Parser mínimo de los CGI JavaScript del router, sin ejecutar JavaScript.

Los CGI (``cgi/cgi_<nombre>.js``) contienen sentencias de nivel superior del tipo::

    var nombre='valor';
    var lista=[['a','b'],null];
    var objeto={'clave':[1,2],otra:"x"};
    addCfg("nombre", "983044000000", "valor");
    nombre={"reasignado":1};

Se extraen los literales (cadenas, números, arrays, objetos, ``null``/``true``/``false``)
y las llamadas ``addCfg``. Las sentencias que no son literales puros (llamadas a
funciones, expresiones) se ignoran.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
import re
from typing import Any
from urllib.parse import unquote

_ASSIGN_RE = re.compile(r"(?m)^[ \t]*(?:var[ \t]+)?([A-Za-z_$][\w$]*)[ \t]*=(?!=)")
_ADDCFG_RE = re.compile(r"\baddCfg\s*\(")
_NUMBER_RE = re.compile(r"-?(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")
_IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")
_BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")

_KEYWORDS: dict[str, Any] = {"null": None, "undefined": None, "true": True, "false": False}
_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


class _NotLiteral(Exception):
    """La expresión no es un literal JS puro."""


@dataclass(slots=True)
class CfgEntry:
    """Entrada ``addCfg(nombre, id, valor[, cifrado])``."""

    id: str
    raw_value: str
    encrypted: bool = False

    @property
    def value(self) -> str:
        """Valor tal y como lo devuelve ``getCfg`` en la web (URI-decoded)."""
        return uri_decode(self.raw_value)


@dataclass(slots=True)
class JsDocument:
    """Resultado de parsear un CGI."""

    vars: dict[str, Any] = field(default_factory=dict)
    cfg: dict[str, CfgEntry] = field(default_factory=dict)

    def var(self, name: str, default: Any = None) -> Any:
        return self.vars.get(name, default)

    def cfg_value(self, name: str, default: str | None = None) -> str | None:
        entry = self.cfg.get(name)
        return entry.value if entry is not None else default

    def merge(self, other: JsDocument) -> None:
        self.vars.update(other.vars)
        self.cfg.update(other.cfg)


def uri_decode(value: str) -> str:
    """Equivalente a ``decodeURIComponent`` con *fallback* al valor original."""
    if "%" not in value or _BAD_PERCENT_RE.search(value):
        return value
    try:
        return unquote(value, errors="strict")
    except UnicodeDecodeError:
        return value


class _LiteralParser:
    def __init__(self, text: str, pos: int = 0) -> None:
        self.text = text
        self.pos = pos

    # --- utilidades -----------------------------------------------------------------
    def _peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def skip_ws(self) -> None:
        text, n = self.text, len(self.text)
        while self.pos < n:
            c = text[self.pos]
            if c in " \t\r\n﻿\xa0":
                self.pos += 1
            elif text.startswith("//", self.pos):
                end = text.find("\n", self.pos)
                self.pos = n if end < 0 else end + 1
            elif text.startswith("/*", self.pos):
                end = text.find("*/", self.pos + 2)
                self.pos = n if end < 0 else end + 2
            else:
                break

    # --- literales ------------------------------------------------------------------
    def value(self) -> Any:
        self.skip_ws()
        c = self._peek()
        if c in ("'", '"'):
            return self._string()
        if c == "[":
            return self._array()
        if c == "{":
            return self._object()
        if c and (c.isdigit() or c in "-."):
            return self._number()
        m = _IDENT_RE.match(self.text, self.pos)
        if m and m.group(0) in _KEYWORDS:
            self.pos = m.end()
            return _KEYWORDS[m.group(0)]
        raise _NotLiteral

    def _string(self) -> str:
        quote = self.text[self.pos]
        self.pos += 1
        out: list[str] = []
        text, n = self.text, len(self.text)
        while self.pos < n:
            c = text[self.pos]
            if c == quote:
                self.pos += 1
                return "".join(out)
            if c == "\\":
                self.pos += 1
                if self.pos >= n:
                    break
                e = text[self.pos]
                if e == "x" and self.pos + 2 < n:
                    out.append(chr(int(text[self.pos + 1 : self.pos + 3], 16)))
                    self.pos += 3
                    continue
                if e == "u" and self.pos + 4 < n:
                    out.append(chr(int(text[self.pos + 1 : self.pos + 5], 16)))
                    self.pos += 5
                    continue
                if e == "\r" and text.startswith("\r\n", self.pos):
                    self.pos += 2
                    continue
                if e == "\n":
                    self.pos += 1
                    continue
                out.append(_ESCAPES.get(e, e))
                self.pos += 1
                continue
            if c == "\n":
                raise _NotLiteral
            out.append(c)
            self.pos += 1
        raise _NotLiteral

    def _number(self) -> int | float:
        m = _NUMBER_RE.match(self.text, self.pos)
        if not m:
            raise _NotLiteral
        self.pos = m.end()
        token = m.group(0)
        if token.lower().lstrip("-").startswith("0x"):
            return int(token, 16)
        if any(ch in token for ch in ".eE"):
            return float(token)
        return int(token)

    def _array(self) -> list[Any]:
        self.pos += 1
        items: list[Any] = []
        while True:
            self.skip_ws()
            c = self._peek()
            if c == "]":
                self.pos += 1
                return items
            if c == ",":  # elisión: [a,,b]
                items.append(None)
                self.pos += 1
                continue
            items.append(self.value())
            self.skip_ws()
            c = self._peek()
            if c == ",":
                self.pos += 1
            elif c != "]":
                raise _NotLiteral

    def _object(self) -> dict[str, Any]:
        self.pos += 1
        obj: dict[str, Any] = {}
        while True:
            self.skip_ws()
            c = self._peek()
            if c == "}":
                self.pos += 1
                return obj
            if c in ("'", '"'):
                key = self._string()
            elif c and (c.isdigit() or c == "-"):
                key = str(self._number())
            else:
                m = _IDENT_RE.match(self.text, self.pos)
                if not m:
                    raise _NotLiteral
                key = m.group(0)
                self.pos = m.end()
            self.skip_ws()
            if self._peek() != ":":
                raise _NotLiteral
            self.pos += 1
            obj[key] = self.value()
            self.skip_ws()
            c = self._peek()
            if c == ",":
                self.pos += 1
            elif c != "}":
                raise _NotLiteral


def _statement_ends(text: str, pos: int) -> bool:
    """Tras un literal debe terminar la sentencia (``;``, salto de línea, ``}`` o EOF)."""
    n = len(text)
    while pos < n and text[pos] in " \t\r":
        pos += 1
    return pos >= n or text[pos] in ";\n}"


def _depth_map(text: str) -> list[tuple[int, int]] | None:
    """Devuelve [(posición, profundidad)] en cada cambio de llaves, saltando cadenas y
    comentarios. ``None`` si las llaves no cuadran (p. ej. una regex con llaves)."""
    changes: list[tuple[int, int]] = [(0, 0)]
    depth = 0
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in ("'", '"'):
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == "{":
            depth += 1
            changes.append((i + 1, depth))
        elif c == "}":
            depth -= 1
            if depth < 0:
                return None
            changes.append((i + 1, depth))
        i += 1
    return changes if depth == 0 else None


def _depth_at(changes: list[tuple[int, int]], pos: int) -> int:
    idx = bisect_right(changes, (pos, float("inf"))) - 1
    return changes[idx][1] if idx >= 0 else 0


def parse_js(text: str) -> JsDocument:
    """Extrae variables literales y entradas ``addCfg`` de un CGI."""
    doc = JsDocument()
    changes = _depth_map(text)

    for m in _ASSIGN_RE.finditer(text):
        if changes is not None and _depth_at(changes, m.start()) != 0:
            continue
        parser = _LiteralParser(text, m.end())
        try:
            value = parser.value()
        except (_NotLiteral, ValueError):
            continue
        if _statement_ends(text, parser.pos):
            doc.vars[m.group(1)] = value

    for m in _ADDCFG_RE.finditer(text):
        parser = _LiteralParser(text, m.end())
        args: list[Any] = []
        try:
            while True:
                args.append(parser.value())
                parser.skip_ws()
                c = parser._peek()
                parser.pos += 1
                if c == ")":
                    break
                if c != ",":
                    raise _NotLiteral
        except (_NotLiteral, ValueError):
            continue
        if len(args) < 3 or not isinstance(args[0], str):
            continue
        doc.cfg[args[0]] = CfgEntry(
            id=str(args[1]),
            raw_value="" if args[2] is None else str(args[2]),
            encrypted=bool(args[3]) if len(args) > 3 else False,
        )
    return doc

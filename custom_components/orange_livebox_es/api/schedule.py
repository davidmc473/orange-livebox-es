"""Horarios de acceso del control parental (spec 004).

El router guarda cada día como 24 bits en hexadecimal (6 dígitos): el bit más
significativo es la franja 00:00–01:00 y un ``1`` significa *acceso permitido*.
Aquí se usan franjas legibles de horas con fin exclusivo: ``"8-14,16-22"``.
"""

from __future__ import annotations

import re

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
ALL_ALLOWED = "FFFFFF"
ALL_BLOCKED = "000000"

_RANGE_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$")


def ranges_to_hex(ranges: str) -> str:
    """``"8-14,16-22"`` → hex de 24 bits. ``""`` o ``"-"`` = bloqueado todo el día.

    Lanza ``ValueError`` si alguna franja no es válida.
    """
    if ranges.strip() in ("", "-"):
        return ALL_BLOCKED
    bits = [0] * 24
    for part in filter(None, (p.strip() for p in ranges.split(","))):
        match = _RANGE_RE.match(part)
        if match is None:
            raise ValueError(f"Franja no válida: {part!r} (formato: 8-14)")
        start, end = int(match.group(1)), int(match.group(2))
        if not 0 <= start < end <= 24:
            raise ValueError(f"Franja no válida: {part!r} (horas 0-24 y inicio < fin)")
        for hour in range(start, end):
            bits[hour] = 1
    return f"{int(''.join(map(str, bits)), 2):06X}"


def hex_to_ranges(value: str) -> str:
    """Inverso de :func:`ranges_to_hex` (``"000000"`` → ``""``)."""
    try:
        number = int(value, 16)
    except ValueError:
        return ""
    bits = f"{number:024b}"[-24:]
    ranges: list[str] = []
    start: int | None = None
    for hour, bit in enumerate([*bits, "0"]):
        if bit == "1" and start is None:
            start = hour
        elif bit != "1" and start is not None:
            ranges.append(f"{start}-{hour}")
            start = None
    return ",".join(ranges)


def is_allowed(schedule: list[str], weekday: int, hour: int) -> bool:
    """¿Está permitido el acceso el día ``weekday`` (0 = lunes) a la hora ``hour``?"""
    if not 0 <= weekday < len(schedule):
        return True
    try:
        number = int(schedule[weekday] or ALL_BLOCKED, 16)
    except ValueError:
        return True
    return bool(number >> (23 - hour) & 1)

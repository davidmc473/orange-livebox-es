"""Tests de los horarios del control parental (spec 004)."""

from __future__ import annotations

import pytest

from custom_components.orange_livebox_es.api.models import AccessMode, AccessRule
from custom_components.orange_livebox_es.api.schedule import (
    ALL_ALLOWED,
    ALL_BLOCKED,
    hex_to_ranges,
    is_allowed,
    ranges_to_hex,
)


@pytest.mark.parametrize(
    ("ranges", "expected"),
    [
        ("0-24", ALL_ALLOWED),
        ("", ALL_BLOCKED),
        ("-", ALL_BLOCKED),
        ("8-16", "00FF00"),  # bit más significativo = 00:00
        ("0-1", "800000"),
        ("23-24", "000001"),
        ("8-14, 16-22", "00FCFC"),
    ],
)
def test_ranges_to_hex(ranges: str, expected: str) -> None:
    assert ranges_to_hex(ranges) == expected


@pytest.mark.parametrize("bad", ["8", "14-8", "8-25", "a-b", "8-8"])
def test_ranges_to_hex_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        ranges_to_hex(bad)


@pytest.mark.parametrize("ranges", ["0-24", "8-14,16-22", "0-1,23-24", "7-8"])
def test_roundtrip(ranges: str) -> None:
    assert hex_to_ranges(ranges_to_hex(ranges)) == ranges


def test_hex_to_ranges_blocked() -> None:
    assert hex_to_ranges(ALL_BLOCKED) == ""


def test_is_allowed() -> None:
    schedule = [ranges_to_hex("8-16")] + [ALL_BLOCKED] * 6
    assert is_allowed(schedule, 0, 8)
    assert not is_allowed(schedule, 0, 7)
    assert not is_allowed(schedule, 0, 16)
    assert not is_allowed(schedule, 1, 12)


def test_rule_modes() -> None:
    assert AccessRule(0, "M", [ALL_BLOCKED] * 7).mode is AccessMode.BLOCKED
    assert AccessRule(0, "M", [""] * 7).mode is AccessMode.BLOCKED
    assert AccessRule(0, "M", [ALL_ALLOWED] * 7).mode is AccessMode.ALLOWED
    assert AccessRule(0, "M", ["00FF00"] + [ALL_ALLOWED] * 6).mode is AccessMode.SCHEDULED

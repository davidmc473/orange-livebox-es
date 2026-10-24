"""Redacción de datos sensibles (constitución III)."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "**REDACTED**"

#: nombres (variables JS o claves addCfg) cuyo valor nunca debe salir del cliente
_SENSITIVE_NAME_RE = re.compile(
    r"(sharedkey|wepkey|passphrase|psk|passw|pwd|pswd|secret|pin(?!g)|remote_user|"
    r"username|user_id|serial|gpon_sn|\bsn\b|defroute_wan_ip|wan_ip|ipv6_info_buf|"
    r"register_status|display_name|ssid|essid|mac(?!filter)|hostname|station_name|"
    r"device_name|alias_name|client_|online_client|dhcp_client|dhcp_leasetime|"
    r"station_ip|device_ip|phone|number|dns|\bname\b|_name|ipv4|ipv6|\bip\b|"
    # en la topología WiFi/mesh los identificadores de nodo son MAC
    r"device_id|parent_id|child_id|\bpid\b)",
    re.IGNORECASE,
)

#: claves que son secretos de verdad (credenciales) — se redactan incluso en logs debug
SECRET_NAME_RE = re.compile(
    r"(sharedkey|wepkey|passphrase|psk|passw|pwd|pswd|secret|wpsdevpin|remote_user)",
    re.IGNORECASE,
)


def is_sensitive(name: str) -> bool:
    return bool(_SENSITIVE_NAME_RE.search(name))


def redact_tree(value: Any, key: str = "") -> Any:
    """Redacta recursivamente cualquier valor cuya clave parezca sensible."""
    if key and is_sensitive(key):
        if isinstance(value, (dict, list)):
            return REDACTED if not value else _redact_container_values(value)
        return REDACTED if value not in (None, "", "0") else value
    if isinstance(value, dict):
        return {k: redact_tree(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_tree(v, key) for v in value]
    return value


def _redact_container_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _redact_container_values(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_container_values(v) for v in value]
    return REDACTED if value not in (None, "", "0") else value


def mask_number(number: str, visible: int = 3) -> str:
    """``+34900000123`` → ``*********123``."""
    digits = number.strip()
    if len(digits) <= visible:
        return digits
    return "*" * (len(digits) - visible) + digits[-visible:]

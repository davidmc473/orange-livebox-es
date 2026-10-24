"""Excepciones de la capa de acceso al router."""

from __future__ import annotations


class LiveboxError(Exception):
    """Error genérico del router."""


class CannotConnect(LiveboxError):
    """No se puede contactar con el router (timeout, red, HTTP inesperado)."""


class InvalidAuth(LiveboxError):
    """El router ha rechazado las credenciales."""


class LoginLocked(LiveboxError):
    """El router ha bloqueado el login temporalmente tras varios fallos."""

    def __init__(self, seconds: int) -> None:
        super().__init__(f"Login bloqueado durante {seconds} s")
        self.seconds = seconds


class SessionExpired(LiveboxError):
    """La sesión ha caducado (redirección a la página de login)."""


class SessionConflict(LiveboxError):
    """Otra sesión de administración ocupa el router (spec 003).

    El router solo admite una sesión activa: un login desde otro navegador expulsa al
    anterior y, a veces, rechaza el login nuevo como si la contraseña fuera incorrecta.
    """


class UnsupportedRouter(LiveboxError):
    """El equipo responde pero no es un modelo soportado."""


class ParseError(LiveboxError):
    """La respuesta del router no tiene el formato esperado."""

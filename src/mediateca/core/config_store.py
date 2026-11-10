from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mediateca.core.config import settings
from mediateca.core.logging import get_logger
from mediateca.core.models import AppConfig

logger = get_logger(__name__)

FLARESOLVERR_URL_KEY = "flaresolverr_url"
MAX_URL_LENGTH = 2000


class ConfigValidationError(ValueError):
    pass


def normalize_flaresolverr_url(value: str | None) -> str | None:
    """Valida y normaliza una URL base de FlareSolverr."""
    if value is None:
        return None

    candidate = value.strip()
    if not candidate:
        return None
    if len(candidate) > MAX_URL_LENGTH:
        raise ConfigValidationError(
            f"La URL de FlareSolverr no puede superar {MAX_URL_LENGTH} caracteres"
        )
    if any(char.isspace() for char in candidate):
        raise ConfigValidationError("La URL de FlareSolverr no puede contener espacios")

    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ConfigValidationError("La URL de FlareSolverr debe usar http o https")
    if not parsed.hostname:
        raise ConfigValidationError("La URL de FlareSolverr debe incluir un host")
    if parsed.username or parsed.password:
        raise ConfigValidationError(
            "La URL de FlareSolverr no puede incluir credenciales"
        )
    if parsed.query or parsed.fragment:
        raise ConfigValidationError(
            "La URL de FlareSolverr no puede incluir parametros ni fragmentos"
        )
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ConfigValidationError("El puerto de FlareSolverr no es valido") from exc

    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def get_config_value(session: Session, key: str) -> str | None:
    value = session.scalar(select(AppConfig.value).where(AppConfig.key == key))
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def set_config_value(session: Session, key: str, value: str | None) -> None:
    text = value.strip() if value is not None else ""
    if not text:
        session.execute(delete(AppConfig).where(AppConfig.key == key))
        session.flush()
        return

    current = session.get(AppConfig, key)
    if current is None:
        session.add(AppConfig(key=key, value=text))
    else:
        current.value = text
    session.flush()


def _normalize_saved(value: str) -> str | None:
    try:
        return normalize_flaresolverr_url(value)
    except ConfigValidationError:
        logger.warning("La URL de FlareSolverr persistida no es valida; se ignora")
        return None


def effective_flaresolverr_url(session: Session) -> str | None:
    saved = get_config_value(session, FLARESOLVERR_URL_KEY)
    if saved:
        normalized = _normalize_saved(saved)
        if normalized:
            return normalized

    if not settings.flaresolverr_url:
        return None
    try:
        return normalize_flaresolverr_url(settings.flaresolverr_url)
    except ConfigValidationError:
        logger.warning("La URL de FlareSolverr de entorno no es valida; se ignora")
        return None

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime

from mediateca_shared.models import (
    Biblioteca,
    Edicion,
    EdicionMateria,
    EdicionPersona,
    Ejemplar,
    Enlace,
    Materia,
    Obra,
    Persona,
)
from mediateca_shared.soportes import soporte_principal
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediateca.catalog.jobs import mark_enriched
from mediateca.catalog.parser import ParsedEdicion


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.casefold().strip()


def normalize_name(value: str) -> str:
    text = _fold(value)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slugify(value: str) -> str:
    text = _fold(value)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "desconocida"


def _external_key(parsed: ParsedEdicion, ejemplar) -> str:
    raw = "|".join(
        [
            parsed.titn,
            ejemplar.biblioteca_codigo or "",
            ejemplar.sucursal_codigo or "",
            ejemplar.signatura or "",
            ejemplar.soporte or "",
            ejemplar.tipo_ejemplar or "",
            ejemplar.codigo_barras or "",
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _director_principal(parsed: ParsedEdicion) -> str | None:
    for persona in parsed.personas:
        for role in persona.roles:
            if "director" in role.casefold():
                return persona.nombre
    return None


def get_or_create_obra(session: Session, parsed: ParsedEdicion) -> Obra:
    titulo = parsed.titulo_uniforme or parsed.titulo
    stmt = select(Obra).where(Obra.titulo_uniforme == titulo)
    if parsed.anio is None:
        stmt = stmt.where(Obra.anio.is_(None))
    else:
        stmt = stmt.where(Obra.anio == parsed.anio)

    with session.no_autoflush:
        obra = session.scalars(stmt).first()
        if obra is None:
            obra = Obra(
                titulo_uniforme=titulo,
                anio=parsed.anio,
                director_principal=_director_principal(parsed),
            )
            session.add(obra)
            session.flush()
        elif obra.director_principal is None:
            obra.director_principal = _director_principal(parsed)
    return obra


def get_or_create_biblioteca(
    session: Session, codigo: str | None, nombre: str
) -> Biblioteca:
    code = codigo if codigo and codigo != "DESCONOCIDA" else slugify(nombre)
    biblioteca = session.scalars(
        select(Biblioteca).where(Biblioteca.codigo == code)
    ).first()
    if biblioteca is None:
        biblioteca = Biblioteca(codigo=code, nombre=nombre)
        session.add(biblioteca)
        session.flush()
    elif nombre and biblioteca.nombre != nombre:
        biblioteca.nombre = nombre
    return biblioteca


def _get_or_create_persona(session: Session, nombre: str) -> Persona:
    normalized = normalize_name(nombre)
    persona = session.scalars(
        select(Persona).where(Persona.nombre_normalizado == normalized)
    ).first()
    if persona is None:
        persona = Persona(nombre=nombre, nombre_normalizado=normalized)
        session.add(persona)
        session.flush()
    return persona


def _get_or_create_materia(session: Session, termino: str) -> Materia:
    clean_termino = termino.strip()
    normalized = clean_termino.casefold()
    materia = session.scalars(
        select(Materia).where(func.lower(Materia.termino) == normalized)
    ).first()
    if materia is None:
        materia = Materia(termino=clean_termino)
        session.add(materia)
        session.flush()
    elif materia.termino != clean_termino:
        materia.termino = clean_termino
    return materia


def _sync_personas(session: Session, edicion: Edicion, parsed: ParsedEdicion) -> None:
    order = 0
    for parsed_persona in parsed.personas:
        persona = _get_or_create_persona(session, parsed_persona.nombre)
        for role in parsed_persona.roles or ["autor"]:
            edicion.personas.append(
                EdicionPersona(persona=persona, rol=role, orden=order)
            )
            order += 1


def _sync_materias(session: Session, edicion: Edicion, parsed: ParsedEdicion) -> None:
    for termino in parsed.materias:
        materia = _get_or_create_materia(session, termino)
        edicion.materias.append(EdicionMateria(materia=materia))


def _sync_enlaces(edicion: Edicion, parsed: ParsedEdicion) -> None:
    for parsed_enlace in parsed.enlaces:
        edicion.enlaces.append(
            Enlace(url=parsed_enlace.url, etiqueta=parsed_enlace.etiqueta)
        )


def _sync_ejemplares(session: Session, edicion: Edicion, parsed: ParsedEdicion) -> None:
    existing = {ejemplar.external_key: ejemplar for ejemplar in edicion.ejemplares}
    seen_keys: set[str] = set()

    for parsed_ejemplar in parsed.ejemplares:
        key = _external_key(parsed, parsed_ejemplar)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        biblioteca = get_or_create_biblioteca(
            session,
            parsed_ejemplar.biblioteca_codigo,
            parsed_ejemplar.biblioteca_nombre,
        )
        ejemplar = existing.get(key)
        if ejemplar is None:
            ejemplar = Ejemplar(
                external_key=key,
                biblioteca=biblioteca,
                sucursal_codigo=parsed_ejemplar.sucursal_codigo,
                sucursal_nombre=parsed_ejemplar.sucursal_nombre,
                localizacion=parsed_ejemplar.localizacion,
                signatura=parsed_ejemplar.signatura,
                tipo_ejemplar=parsed_ejemplar.tipo_ejemplar,
                soporte=parsed_ejemplar.soporte,
            )
            edicion.ejemplares.append(ejemplar)
        else:
            ejemplar.biblioteca = biblioteca
            ejemplar.sucursal_codigo = parsed_ejemplar.sucursal_codigo
            ejemplar.sucursal_nombre = parsed_ejemplar.sucursal_nombre
            ejemplar.localizacion = parsed_ejemplar.localizacion
            ejemplar.signatura = parsed_ejemplar.signatura
            ejemplar.tipo_ejemplar = parsed_ejemplar.tipo_ejemplar
            ejemplar.soporte = parsed_ejemplar.soporte


def upsert_edicion(session: Session, parsed: ParsedEdicion) -> Edicion:
    obra = get_or_create_obra(session, parsed)

    edicion = session.scalars(
        select(Edicion).where(Edicion.titn == parsed.titn)
    ).first()
    if edicion is None:
        edicion = Edicion(titn=parsed.titn, titulo=parsed.titulo, obra=obra)
        session.add(edicion)

    edicion.obra = obra
    edicion.titulo = parsed.titulo
    edicion.titulo_uniforme = parsed.titulo_uniforme
    edicion.publicacion = parsed.publicacion
    edicion.anio = parsed.anio
    edicion.idioma = parsed.idioma
    edicion.pais = parsed.pais
    edicion.duracion_min = parsed.duracion_min
    edicion.edad_recomendada = parsed.edad_recomendada
    edicion.sinopsis = parsed.sinopsis
    edicion.generos = parsed.generos
    edicion.soportes = parsed.soportes
    edicion.soporte_principal = soporte_principal(parsed.soportes)
    edicion.ean = parsed.ean
    edicion.tipo_documento = parsed.tipo_documento
    edicion.notas = parsed.notas
    edicion.marc = parsed.marc
    edicion.source_url = parsed.source_url

    edicion.personas.clear()
    edicion.materias.clear()
    edicion.enlaces.clear()
    session.flush()

    _sync_personas(session, edicion, parsed)
    _sync_materias(session, edicion, parsed)
    _sync_enlaces(edicion, parsed)
    _sync_ejemplares(session, edicion, parsed)

    timestamp = datetime.now(UTC)
    if edicion.discovery_seen_at is None:
        edicion.discovery_seen_at = timestamp
    mark_enriched(session, edicion, fetched_at=timestamp)

    session.flush()
    return edicion


def upsert_stub(session: Session, parsed: ParsedEdicion) -> Edicion:
    timestamp = datetime.now(UTC)
    edicion = session.scalars(
        select(Edicion).where(Edicion.titn == parsed.titn)
    ).first()

    if edicion is None:
        edicion = Edicion(
            titn=parsed.titn,
            titulo=parsed.titulo,
            publicacion=parsed.publicacion,
            anio=parsed.anio,
            idioma=parsed.idioma,
            pais=parsed.pais,
            duracion_min=parsed.duracion_min,
            generos=parsed.generos,
            soportes=parsed.soportes,
            soporte_principal=soporte_principal(parsed.soportes),
            ean=parsed.ean,
            tipo_documento=parsed.tipo_documento,
            notas=parsed.notas,
            marc=parsed.marc,
            source_url=parsed.source_url,
            is_stub=True,
            discovery_seen_at=timestamp,
        )
        session.add(edicion)
        session.flush()
        return edicion

    edicion.discovery_seen_at = timestamp
    edicion.missing_at = None

    if edicion.is_stub:
        edicion.titulo = parsed.titulo or edicion.titulo
        edicion.publicacion = parsed.publicacion
        edicion.anio = parsed.anio
        edicion.idioma = parsed.idioma
        edicion.pais = parsed.pais
        edicion.duracion_min = parsed.duracion_min
        edicion.generos = parsed.generos
        edicion.soportes = parsed.soportes
        edicion.soporte_principal = soporte_principal(parsed.soportes)
        edicion.ean = parsed.ean
        edicion.tipo_documento = parsed.tipo_documento
        edicion.notas = parsed.notas
        edicion.marc = parsed.marc
        edicion.source_url = parsed.source_url

    session.flush()
    return edicion


def mark_absent_since(
    session: Session,
    seen_titns: Iterable[str],
    *,
    since: datetime,
    missing_at: datetime | None = None,
) -> int:
    """Marca como ausentes las ediciones no vistas desde ``since``."""
    seen = set(seen_titns)
    stmt = select(Edicion).where(
        Edicion.discovery_seen_at.is_not(None),
        Edicion.discovery_seen_at < since,
    )
    if seen:
        stmt = stmt.where(Edicion.titn.not_in(seen))

    timestamp = missing_at or datetime.now(UTC)
    ausentes = 0
    for edicion in session.scalars(stmt):
        if edicion.missing_at is None:
            edicion.missing_at = timestamp
            ausentes += 1
    session.flush()
    return ausentes


def select_pending_titns(
    session: Session,
    *,
    limit: int = 5000,
    after_titn: str | None = None,
    since: datetime | None = None,
) -> list[str]:
    """Devuelve hasta ``limit`` TITN pendientes de enriquecer, ordenados por TITN."""
    stmt = select(Edicion.titn).where(Edicion.detail_fetched_at.is_(None))
    if after_titn is not None:
        stmt = stmt.where(Edicion.titn > after_titn)
    if since is not None:
        stmt = stmt.where(Edicion.discovery_seen_at >= since)
    stmt = stmt.order_by(Edicion.titn).limit(limit)
    return list(session.scalars(stmt))


def count_pending_titns(
    session: Session,
    *,
    since: datetime | None = None,
) -> int:
    stmt = select(func.count(Edicion.id)).where(Edicion.detail_fetched_at.is_(None))
    if since is not None:
        stmt = stmt.where(Edicion.discovery_seen_at >= since)
    return int(session.scalar(stmt) or 0)

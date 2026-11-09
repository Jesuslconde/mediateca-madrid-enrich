from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from mediateca_shared.models import (
    Edicion,
    EdicionMateria,
    EdicionPersona,
    Ejemplar,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mediateca.core.config import settings
from mediateca.core.search import get_index, get_meili_client

FACET_FIELDS = ["soportes", "generos", "anio", "idioma", "bibliotecas"]

FILTERABLE_ATTRIBUTES = [
    "soportes",
    "soporte_principal",
    "generos",
    "anio",
    "idioma",
    "pais",
    "bibliotecas",
    "edad_recomendada",
    "duracion_min",
]

SEARCHABLE_ATTRIBUTES = [
    "titulo",
    "titulo_uniforme",
    "sinopsis",
    "directores",
    "actores",
    "guionistas",
    "personas_texto",
    "materias",
    "generos",
    "publicacion",
]

SORTABLE_ATTRIBUTES = ["anio", "titulo", "duracion_min"]


DIRECTOR_ROLES = {"director", "directora", "director de cine", "directora de cine"}
ACTOR_ROLES = {"actor", "actriz"}
WRITER_ROLES = {"guionista", "guion", "guionista cinematografico", "guionista cinematográfico"}


def _names_by_role(personas: list[dict[str, str]], roles: set[str]) -> list[str]:
    result: list[str] = []
    for persona in personas:
        if persona["rol"].casefold().strip() in roles:
            if persona["nombre"] not in result:
                result.append(persona["nombre"])
    return result


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def build_document(edicion: Edicion) -> dict[str, Any]:
    personas = [
        {"nombre": relacion.persona.nombre, "rol": relacion.rol}
        for relacion in edicion.personas
    ]
    directores = _names_by_role(personas, DIRECTOR_ROLES)
    actores = _names_by_role(personas, ACTOR_ROLES)
    guionistas = _names_by_role(personas, WRITER_ROLES)

    soportes = list(edicion.soportes or [])
    if not soportes:
        soportes = sorted(
            {ejemplar.soporte for ejemplar in edicion.ejemplares if ejemplar.soporte}
        )

    bibliotecas = sorted(
        {ejemplar.biblioteca.nombre for ejemplar in edicion.ejemplares}
    )
    materias = [relacion.materia.termino for relacion in edicion.materias]

    return {
        "id": edicion.titn,
        "titn": edicion.titn,
        "titulo": edicion.titulo,
        "titulo_uniforme": edicion.titulo_uniforme,
        "publicacion": edicion.publicacion,
        "anio": edicion.anio,
        "idioma": edicion.idioma,
        "pais": edicion.pais,
        "duracion_min": edicion.duracion_min,
        "edad_recomendada": edicion.edad_recomendada,
        "sinopsis": edicion.sinopsis,
        "generos": edicion.generos or [],
        "materias": materias,
        "soportes": soportes,
        "soporte_principal": edicion.soporte_principal,
        "ean": edicion.ean,
        "tipo_documento": edicion.tipo_documento,
        "personas": personas,
        "personas_texto": _dedupe([persona["nombre"] for persona in personas]),
        "directores": directores,
        "actores": actores,
        "guionistas": guionistas,
        "bibliotecas": bibliotecas,
        "ejemplares": len(edicion.ejemplares),
        "detail_complete": edicion.detail_fetched_at is not None,
        "is_stub": edicion.detail_fetched_at is None or bool(edicion.is_stub),
        "updated_at": edicion.updated_at.isoformat() if edicion.updated_at else None,
    }


def _quote(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_filters(
    *,
    soportes: list[str] | None = None,
    genero: str | None = None,
    anio_desde: int | None = None,
    anio_hasta: int | None = None,
    idioma: str | None = None,
    biblioteca: str | None = None,
) -> str | None:
    filters: list[str] = []

    if soportes:
        filters.append(
            "(" + " OR ".join(f"soportes = {_quote(item)}" for item in soportes) + ")"
        )
    if genero:
        filters.append(f"generos = {_quote(genero)}")
    if idioma:
        filters.append(f"idioma = {_quote(idioma)}")
    if biblioteca:
        filters.append(f"bibliotecas = {_quote(biblioteca)}")
    if anio_desde is not None:
        filters.append(f"anio >= {int(anio_desde)}")
    if anio_hasta is not None:
        filters.append(f"anio <= {int(anio_hasta)}")

    return " AND ".join(filters) if filters else None


class MeiliIndexer:
    def __init__(self) -> None:
        self.client = get_meili_client()
        self.index = get_index()

    def ensure_index(self) -> None:
        try:
            self.client.create_index(
                settings.meilisearch_index, {"primaryKey": "id"}
            )
        except Exception:
            # Si ya existe, create_index lanza un error de API; es seguro continuar.
            pass

        task = self.index.update_settings(
            {
                "filterableAttributes": FILTERABLE_ATTRIBUTES,
                "searchableAttributes": SEARCHABLE_ATTRIBUTES,
                "sortableAttributes": SORTABLE_ATTRIBUTES,
                "faceting": {"maxValuesPerFacet": 100},
                "rankingRules": [
                    "words",
                    "typo",
                    "proximity",
                    "attribute",
                    "sort",
                    "exactness",
                ],
            }
        )
        self._wait(task)

    def _wait(self, task: Any) -> None:
        task_uid = getattr(task, "task_uid", None) or getattr(task, "uid", None)
        if task_uid is not None:
            self.client.wait_for_task(task_uid)

    def _add_batch(self, documents: list[dict[str, Any]]) -> None:
        if not documents:
            return
        task = self.index.add_documents(documents, primary_key="id")
        self._wait(task)

    def delete_all(self) -> None:
        task = self.index.delete_all_documents()
        self._wait(task)

    def index_editions(self, session: Session, *, reset: bool = False) -> int:
        self.ensure_index()
        if reset:
            self.delete_all()

        stmt = select(Edicion).options(
            selectinload(Edicion.ejemplares).selectinload(Ejemplar.biblioteca),
            selectinload(Edicion.personas).selectinload(EdicionPersona.persona),
            selectinload(Edicion.materias).selectinload(EdicionMateria.materia),
        )

        total = 0
        batch: list[dict[str, Any]] = []
        for edicion in session.scalars(stmt).yield_per(200):
            batch.append(build_document(edicion))
            total += 1
            if len(batch) >= 200:
                self._add_batch(batch)
                batch = []
        self._add_batch(batch)
        return total

    def index_titns(self, session: Session, titns: Iterable[str]) -> int:
        """Indexa solo las ediciones indicadas, en lotes de 200."""
        self.ensure_index()
        unique = list(dict.fromkeys(titn for titn in titns if titn))

        total = 0
        for start in range(0, len(unique), 200):
            chunk = unique[start : start + 200]
            stmt = (
                select(Edicion)
                .where(Edicion.titn.in_(chunk))
                .options(
                    selectinload(Edicion.ejemplares).selectinload(Ejemplar.biblioteca),
                    selectinload(Edicion.personas).selectinload(EdicionPersona.persona),
                    selectinload(Edicion.materias).selectinload(EdicionMateria.materia),
                )
            )
            documents = [build_document(edicion) for edicion in session.scalars(stmt)]
            self._add_batch(documents)
            total += len(documents)
        return total

    def search(
        self,
        query: str,
        *,
        soportes: list[str] | None = None,
        genero: str | None = None,
        anio_desde: int | None = None,
        anio_hasta: int | None = None,
        idioma: str | None = None,
        biblioteca: str | None = None,
        sort: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> dict[str, Any]:
        filters = build_filters(
            soportes=soportes,
            genero=genero,
            anio_desde=anio_desde,
            anio_hasta=anio_hasta,
            idioma=idioma,
            biblioteca=biblioteca,
        )
        options: dict[str, Any] = {
            "page": max(1, page),
            "hitsPerPage": max(1, min(limit, 100)),
            "facets": FACET_FIELDS,
            "attributesToHighlight": ["titulo", "sinopsis"],
            "highlightPreTag": "<mark>",
            "highlightPostTag": "</mark>",
        }
        if filters:
            options["filter"] = filters
        if sort:
            options["sort"] = [sort]

        result = self.index.search(query or "", options)
        hits = result.get("hits", [])
        total = result.get("estimatedTotalHits", result.get("totalHits", len(hits)))
        return {
            "query": query or "",
            "page": max(1, page),
            "limit": max(1, min(limit, 100)),
            "total": total,
            "total_pages": max(1, math.ceil(total / max(1, limit))),
            "took_ms": result.get("processingTimeMs", 0),
            "facets": result.get("facetDistribution", {}),
            "hits": hits,
        }

    def health(self) -> dict[str, Any]:
        return self.client.health()


def iter_documents(session: Session) -> Iterable[dict[str, Any]]:
    stmt = select(Edicion).options(
        selectinload(Edicion.ejemplares).selectinload(Ejemplar.biblioteca),
        selectinload(Edicion.personas).selectinload(EdicionPersona.persona),
        selectinload(Edicion.materias).selectinload(EdicionMateria.materia),
    )
    for edicion in session.scalars(stmt).yield_per(200):
        yield build_document(edicion)

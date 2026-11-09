from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup, Tag
from mediateca_shared.soportes import (
    canonical_soporte,
    detect_soportes,
)

try:  # lxml es opcional en pruebas; html.parser siempre esta disponible
    import lxml  # noqa: F401

    BS_PARSER = "lxml"
except ImportError:  # pragma: no cover
    BS_PARSER = "html.parser"


MARC_KEY_RE = re.compile(
    r"^(T\d{3}[a-z]*|TITN|LENG|FEPU|ntitl|nauth|nedit|nedic|nisbn|nissn|ld06|ld07)$"
)


@dataclass(slots=True)
class ParsedPersona:
    nombre: str
    roles: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedEjemplar:
    biblioteca_codigo: str
    biblioteca_nombre: str
    sucursal_codigo: str | None
    sucursal_nombre: str | None
    localizacion: str | None
    signatura: str | None
    tipo_ejemplar: str | None
    soporte: str | None
    codigo_barras: str | None = None


@dataclass(slots=True)
class ParsedEnlace:
    url: str
    etiqueta: str | None = None


@dataclass(slots=True)
class ParsedEdicion:
    titn: str
    titulo: str
    titulo_uniforme: str | None = None
    publicacion: str | None = None
    anio: int | None = None
    idioma: str | None = None
    pais: str | None = None
    duracion_min: int | None = None
    edad_recomendada: str | None = None
    sinopsis: str | None = None
    generos: list[str] = field(default_factory=list)
    materias: list[str] = field(default_factory=list)
    soportes: list[str] = field(default_factory=list)
    ean: str | None = None
    tipo_documento: str | None = None
    notas: dict[str, str] = field(default_factory=dict)
    marc: dict[str, Any] = field(default_factory=dict)
    personas: list[ParsedPersona] = field(default_factory=list)
    ejemplares: list[ParsedEjemplar] = field(default_factory=list)
    enlaces: list[ParsedEnlace] = field(default_factory=list)
    source_url: str | None = None

    @property
    def soporte_principal(self) -> str | None:
        if not self.soportes:
            return None
        if len(self.soportes) == 1:
            return self.soportes[0]
        return "Varios"


def clean(value: Any, *, strip_trailing: bool = False) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if strip_trailing:
        text = re.sub(r"\s*[/:;,.]+$", "", text).strip()
    return text or None


def _text(tag: Tag | None, *, strip_trailing: bool = False) -> str | None:
    if tag is None:
        return None
    return clean(tag.get_text(" ", strip=True), strip_trailing=strip_trailing)


def _js_text(soup: BeautifulSoup, key: str) -> str | None:
    return _text(soup.select_one(f"span.js-{key}"))


def _hidden_text(scope: Tag, cls: str) -> str | None:
    return _text(scope.select_one(f"span.{cls}"))


def _dt_dd(soup: BeautifulSoup) -> dict[str, str]:
    data: dict[str, str] = {}
    for dl in soup.select("dl.docu_etiq, div.doc_data dl"):
        for dt in dl.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if dd is None:
                continue
            label = clean(dt.get_text(" ", strip=True))
            value = _text(dd, strip_trailing=True)
            if not label or not value:
                continue
            label = label.rstrip(":")
            data.setdefault(label, value)
    return data


def _marc(soup: BeautifulSoup) -> dict[str, Any]:
    marc: dict[str, Any] = {}
    for span in soup.find_all("span", class_=True):
        classes = span.get("class") or []
        key = next((c[3:] for c in classes if c.startswith("js-")), None)
        if not key or not MARC_KEY_RE.match(key):
            continue
        value = _text(span)
        if not value:
            continue
        if key in marc:
            if not isinstance(marc[key], list):
                marc[key] = [marc[key]]
            marc[key].append(value)
        else:
            marc[key] = value
    return marc


def _parse_personas(soup: BeautifulSoup) -> list[ParsedPersona]:
    merged: dict[str, list[str]] = {}
    for span in soup.select("span.js-T700"):
        anchors = [
            clean(a.get_text(" ", strip=True))
            for a in span.find_all("a")
        ]
        anchors = [a for a in anchors if a and not a.startswith("(+)")]
        if not anchors:
            continue

        name = anchors[0]
        roles = []
        for anchor in anchors[1:]:
            role = anchor.lstrip(",; ").strip()
            if not role or role.startswith("(+)"):
                continue
            roles.append(role)

        if not roles:
            text = clean(span.get_text(" ", strip=True)) or ""
            if "," in text:
                maybe_name, _, maybe_role = text.partition(",")
                maybe_name = clean(maybe_name)
                maybe_role = clean(maybe_role)
                if maybe_name and maybe_role:
                    name = maybe_name
                    roles = [maybe_role]

        for role in roles or ["autor"]:
            merged.setdefault(name, [])
            if role not in merged[name]:
                merged[name].append(role)

    if merged:
        return [ParsedPersona(nombre=name, roles=roles) for name, roles in merged.items()]

    # Fallback: extraer del bloque visible "Autores/Autoras"
    dd = None
    for dt in soup.find_all("dt"):
        if clean(dt.get_text(" ", strip=True) or "") == "Autores/Autoras":
            dd = dt.find_next_sibling("dd")
            break
    if dd is None:
        return []

    anchors = [
        clean(a.get_text(" ", strip=True))
        for a in dd.find_all("a")
        if clean(a.get_text(" ", strip=True))
    ]
    if not anchors:
        return []
    name = anchors[0]
    roles = [a.lstrip(",; ").strip() for a in anchors[1:] if not a.startswith("(+)")]
    return [ParsedPersona(nombre=name, roles=roles or ["autor"])]


def _parse_enlaces(soup: BeautifulSoup) -> list[ParsedEnlace]:
    urls = [clean(s.get_text(" ", strip=True)) for s in soup.select("span.js-T856u")]
    labels = [clean(s.get_text(" ", strip=True)) for s in soup.select("span.js-T856z")]
    result: list[ParsedEnlace] = []
    seen: set[str] = set()
    for index, url in enumerate(urls):
        if not url or url in seen:
            continue
        seen.add(url)
        label = labels[index] if index < len(labels) else None
        result.append(ParsedEnlace(url=url, etiqueta=label))
    return result


def _cell_text(td: Tag) -> str | None:
    for label in td.select(".copias_label"):
        label.extract()
    return clean(td.get_text(" ", strip=True))


def _parse_ejemplares(soup: BeautifulSoup) -> list[ParsedEjemplar]:
    ejemplares: list[ParsedEjemplar] = []

    for block in soup.select("div.copias_data"):
        bib_code = _hidden_text(block, "bicobi") or "DESCONOCIDA"
        bib_name = _hidden_text(block, "bidesc") or "Biblioteca sin nombre"

        for item in block.select("div.c-accordion_item"):
            suc_code = clean(item.get("data-sucosu")) or _hidden_text(item, "sucosu")
            suc_name = _hidden_text(item, "sudesc")
            table = item.find("table")
            if table is None:
                continue

            rows = table.select("tbody tr") or table.find_all("tr")[1:]
            for tr in rows:
                tds = tr.find_all("td", recursive=False)
                if len(tds) < 4:
                    tds = tr.find_all("td")
                if len(tds) < 4:
                    continue

                loc_el = tds[0].select_one(".icm_locSign span")
                localizacion = _text(loc_el)
                sign_a = tds[0].select_one("a[data-sign]")
                signatura = clean(sign_a.get("data-sign")) if sign_a else None
                codigo_barras = clean(sign_a.get("data-bc")) if sign_a else None
                if not signatura:
                    loc_spans = tds[0].select(".icm_locSign span")
                    if len(loc_spans) > 1:
                        signatura = _text(loc_spans[-1])

                tipo_ejemplar = _cell_text(tds[1])
                soporte_raw = _cell_text(tds[2])
                soporte = canonical_soporte(soporte_raw)

                ejemplares.append(
                    ParsedEjemplar(
                        biblioteca_codigo=bib_code,
                        biblioteca_nombre=bib_name,
                        sucursal_codigo=suc_code,
                        sucursal_nombre=suc_name,
                        localizacion=localizacion,
                        signatura=signatura,
                        tipo_ejemplar=tipo_ejemplar,
                        soporte=soporte,
                        codigo_barras=codigo_barras,
                    )
                )

    return ejemplares


def _unique(values: list[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _extract_year(*values: str | None) -> int | None:
    for value in values:
        if not value:
            continue
        match = re.search(r"\b(19\d{2}|20\d{2})\b", value)
        if match:
            return int(match.group(1))
    return None


def _extract_duration(*values: str | None) -> int | None:
    for value in values:
        if not value:
            continue
        match = re.search(r"(\d{1,3})\s*min", value, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _parse_generos(soup: BeautifulSoup, data: dict[str, str], marc: dict[str, Any]) -> list[str]:
    values: list[str | None] = []
    if "Género" in data:
        values.extend(part.strip() for part in data["Género"].split(";"))
    t655 = marc.get("T655")
    if isinstance(t655, str):
        values.append(re.split(r"\s+t[a-z]{2,}", t655)[0])
    elif isinstance(t655, list):
        for item in t655:
            values.append(re.split(r"\s+t[a-z]{2,}", item)[0])
    return _unique(values)


def _parse_materias(soup: BeautifulSoup, data: dict[str, str]) -> list[str]:
    values: list[str | None] = [
        _text(li) for li in soup.select(".doc_icm_T6XX li")
    ]
    if "Materias" in data:
        values.append(data["Materias"])
    return _unique(values)


def parse_detail(html: str, url: str | None = None) -> ParsedEdicion:
    soup = BeautifulSoup(html, BS_PARSER)
    data = _dt_dd(soup)
    marc = _marc(soup)

    titn = _js_text(soup, "TITN")
    if not titn and url:
        match = re.search(r"TITN=(\d+)", url)
        if match:
            titn = match.group(1)
    if not titn:
        raise ValueError("No se ha podido identificar el TITN de la ficha")

    titulo = _js_text(soup, "ntitl") or _text(
        soup.select_one(".doc_title"), strip_trailing=True
    )
    if not titulo:
        raise ValueError(f"La ficha {titn} no tiene titulo")

    descripcion_fisica = (
        data.get("Descripción física")
        or (_js_text(soup, "T300a") or None)
    )
    publicacion = (
        data.get("Publicación")
        or (_js_text(soup, "T260ab") or None)
        or (_js_text(soup, "T260b") or None)
    )

    type_icon = soup.select_one(".doc_type i")
    tipo_documento = clean(type_icon.get("title")) if isinstance(type_icon, Tag) else None

    t008_el = soup.select_one("span.js-T008")
    t008_raw = t008_el.get_text("") if isinstance(t008_el, Tag) else None
    t008 = clean(t008_raw)
    pais = clean(t008_raw[15:17]) if t008_raw and len(t008_raw) >= 17 else None

    idioma = _js_text(soup, "LENG")
    if not idioma and t008_raw and len(t008_raw) >= 38:
        idioma = clean(t008_raw[35:38])

    generos = _parse_generos(soup, data, marc)
    materias = _parse_materias(soup, data)

    ejemplares = _parse_ejemplares(soup)
    soportes = detect_soportes(
        descripcion_fisica,
        [ejemplar.soporte for ejemplar in ejemplares if ejemplar.soporte],
    )

    notas = {
        label: value
        for label, value in data.items()
        if label not in {"Título uniforme", "Título", "Publicación", "Descripción física"}
    }

    enlace_permanente = _text(soup.select_one("#xslike"))

    return ParsedEdicion(
        titn=str(titn),
        titulo=titulo,
        titulo_uniforme=data.get("Título uniforme"),
        publicacion=publicacion,
        anio=_extract_year(
            data.get("Año"),
            _js_text(soup, "T260c"),
            _js_text(soup, "FEPU"),
            t008[:4] if t008 else None,
        ),
        idioma=idioma,
        pais=pais,
        duracion_min=_extract_duration(descripcion_fisica, _js_text(soup, "T300a")),
        edad_recomendada=(
            data.get("Nota del nivel del destinatario")
            or (_js_text(soup, "T521") or None)
        ),
        sinopsis=data.get("Sumario, etc.") or (_js_text(soup, "T520") or None),
        generos=generos,
        materias=materias,
        soportes=soportes,
        ean=_js_text(soup, "T024a"),
        tipo_documento=tipo_documento,
        notas=notas,
        marc=marc,
        personas=_parse_personas(soup),
        ejemplares=ejemplares,
        enlaces=_parse_enlaces(soup),
        source_url=enlace_permanente or url,
    )


def parse_file(path: str, url: str | None = None) -> ParsedEdicion:
    raw = open(path, "rb").read()  # noqa: SIM115
    text: str | None = None
    for encoding in ("utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("latin-1", errors="replace")
    return parse_detail(text, url=url or path)

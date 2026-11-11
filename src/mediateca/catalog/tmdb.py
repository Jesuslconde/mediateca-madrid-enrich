from __future__ import annotations

import difflib
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from mediateca.core.config import settings

TMDB_BASE_URL = "https://api.themoviedb.org"
SIMILARITY_THRESHOLD = 0.90
YEAR_TOLERANCE = 1


class TmdbError(RuntimeError):
    pass


class TmdbAuthError(TmdbError):
    pass


class TmdbNotFoundError(TmdbError):
    pass


@dataclass(slots=True)
class TmdbSearchResult:
    id: int
    title: str
    original_title: str
    release_date: str | None
    popularity: float
    origin_country: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TmdbMovieDetail:
    id: int
    title: str
    original_title: str
    release_date: str | None
    production_countries: list[str] = field(default_factory=list)
    origin_country: list[str] = field(default_factory=list)


def is_jwt_token(token: str) -> bool:
    """Los Read Access Tokens v4 son JWT; las API Key v3 no lo son."""
    return token.startswith("eyJ") and token.count(".") == 2


def _release_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\d{4})", value)
    return int(match.group(1)) if match else None


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_candidates(titulo_uniforme: str | None, titulo: str | None) -> list[str]:
    candidates: list[str] = []
    for raw in (titulo_uniforme, titulo):
        if not raw:
            continue
        cleaned = re.sub(r"\s*[/:;,.]+$", "", raw.strip()).strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)
        head = re.split(r"\s+/\s+", cleaned, maxsplit=1)[0].strip()
        if head and head not in candidates:
            candidates.append(head)
    return candidates


def _result_year(result: TmdbSearchResult) -> int | None:
    return _release_year(result.release_date)


def _matches_year(result: TmdbSearchResult, year: int | None) -> bool:
    result_year = _result_year(result)
    if year is None:
        return True
    return result_year is not None and abs(result_year - year) <= YEAR_TOLERANCE


def _title_score(candidate: str, result: TmdbSearchResult) -> float:
    normalized_candidate = normalize_title(candidate)
    if not normalized_candidate:
        return 0.0
    scores = [
        difflib.SequenceMatcher(None, normalized_candidate, normalize_title(result.title)).ratio(),
        difflib.SequenceMatcher(
            None, normalized_candidate, normalize_title(result.original_title)
        ).ratio(),
    ]
    return max(scores)


def select_best_match(
    candidates: list[str],
    results: list[TmdbSearchResult],
    year: int | None,
) -> TmdbSearchResult | None:
    best: tuple[float, float, TmdbSearchResult] | None = None
    for result in results:
        if not _matches_year(result, year):
            continue
        for candidate in candidates:
            score = _title_score(candidate, result)
            exact = normalize_title(candidate) in {
                normalize_title(result.title),
                normalize_title(result.original_title),
            }
            if not exact and score < SIMILARITY_THRESHOLD:
                continue
            if year is None and not exact:
                continue
            ranked = (1.0 if exact else score, result.popularity, result)
            if best is None or ranked[:2] > best[:2]:
                best = ranked
    return best[2] if best else None


def resolve_countries(detail: TmdbMovieDetail) -> list[str]:
    values = detail.production_countries or detail.origin_country
    countries: list[str] = []
    for value in values:
        code = str(value).strip().upper()
        if code and code not in countries:
            countries.append(code)
    return countries


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    return max(0.0, (target - datetime.now(UTC)).total_seconds())


class TmdbClient:
    def __init__(
        self,
        token: str,
        *,
        language: str | None = None,
        delay: float | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        base_url: str = TMDB_BASE_URL,
        user_agent: str | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.token = token.strip()
        self.language = language or settings.tmdb_language
        self.delay = settings.tmdb_delay if delay is None else delay
        self.timeout = settings.tmdb_timeout if timeout is None else timeout
        self.max_retries = settings.tmdb_max_retries if max_retries is None else max_retries
        self.base_url = base_url.rstrip("/")
        self.sleep = sleep
        self._bearer = is_jwt_token(self.token)
        headers = {"Accept": "application/json", "User-Agent": user_agent or settings.user_agent}
        if self._bearer:
            headers["Authorization"] = f"Bearer {self.token}"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
            transport=transport,
        )

    def __enter__(self) -> TmdbClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _params(self, params: dict[str, Any]) -> dict[str, Any]:
        result = dict(params)
        result["language"] = self.language
        if not self._bearer:
            result["api_key"] = self.token
        return result

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.delay:
            self.sleep(self.delay)
        last_error: Exception | None = None
        for attempt in range(max(1, self.max_retries)):
            try:
                response = self._client.get(path, params=self._params(params))
            except httpx.TimeoutException as exc:
                last_error = exc
                wait = self._backoff(attempt)
            except httpx.TransportError as exc:
                last_error = exc
                wait = self._backoff(attempt)
            else:
                if response.status_code == 429:
                    wait = _retry_after_seconds(response) or self._backoff(attempt)
                    last_error = TmdbError("TMDB ha limitado las peticiones")
                elif response.status_code in {401, 403}:
                    raise TmdbAuthError("El token de TMDB no es valido")
                elif response.status_code == 404:
                    raise TmdbNotFoundError(f"No existe el recurso de TMDB {path}")
                elif response.status_code >= 500:
                    last_error = TmdbError(f"TMDB respondio {response.status_code}")
                    wait = self._backoff(attempt)
                elif response.status_code >= 400:
                    raise TmdbError(f"TMDB respondio {response.status_code}")
                else:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise TmdbError("TMDB devolvio una respuesta no JSON") from exc
                    if not isinstance(payload, dict):
                        raise TmdbError("TMDB devolvio una respuesta inesperada")
                    return payload
            if attempt + 1 < max(1, self.max_retries):
                self.sleep(wait)
        raise TmdbError("No se pudo completar la peticion a TMDB") from last_error

    def _backoff(self, attempt: int) -> float:
        return max(self.delay, 0.1) * (2**attempt)

    def search_movie(self, query: str, *, year: int | None = None) -> list[TmdbSearchResult]:
        params: dict[str, Any] = {"query": query, "include_adult": "false"}
        if year is not None:
            params["year"] = str(year)
        payload = self._request("/3/search/movie", params)
        results = payload.get("results")
        if not isinstance(results, list):
            return []
        parsed: list[TmdbSearchResult] = []
        for item in results:
            if not isinstance(item, dict) or "id" not in item:
                continue
            origin = item.get("origin_country")
            parsed.append(
                TmdbSearchResult(
                    id=int(item["id"]),
                    title=str(item.get("title") or ""),
                    original_title=str(item.get("original_title") or ""),
                    release_date=item.get("release_date") or None,
                    popularity=float(item.get("popularity") or 0.0),
                    origin_country=[str(code) for code in origin] if isinstance(origin, list) else [],
                )
            )
        return parsed

    def get_movie(self, movie_id: int) -> TmdbMovieDetail:
        payload = self._request(f"/3/movie/{movie_id}", {})
        production = payload.get("production_countries")
        origin = payload.get("origin_country")
        return TmdbMovieDetail(
            id=int(payload.get("id") or movie_id),
            title=str(payload.get("title") or ""),
            original_title=str(payload.get("original_title") or ""),
            release_date=payload.get("release_date") or None,
            production_countries=[
                str(item.get("iso_3166_1"))
                for item in production
                if isinstance(item, dict) and item.get("iso_3166_1")
            ]
            if isinstance(production, list)
            else [],
            origin_country=[str(code) for code in origin] if isinstance(origin, list) else [],
        )


def find_movie(
    client: TmdbClient,
    *,
    titulo_uniforme: str | None,
    titulo: str | None,
    anio: int | None,
) -> tuple[TmdbSearchResult, TmdbMovieDetail] | None:
    candidates = title_candidates(titulo_uniforme, titulo)
    if not candidates:
        return None
    results: dict[int, TmdbSearchResult] = {}
    for candidate in candidates:
        for result in client.search_movie(candidate, year=anio):
            results.setdefault(result.id, result)
    match = select_best_match(candidates, list(results.values()), anio)
    if match is None:
        return None
    return match, client.get_movie(match.id)

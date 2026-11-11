from __future__ import annotations

import logging

import httpx
import pytest

from mediateca.catalog.tmdb import (
    TmdbAuthError,
    TmdbClient,
    TmdbMovieDetail,
    TmdbSearchResult,
    find_movie,
    is_jwt_token,
    normalize_title,
    resolve_countries,
    select_best_match,
    title_candidates,
)
from mediateca.core.config import Settings


def _client(handler, **kwargs) -> TmdbClient:
    transport = httpx.MockTransport(handler)
    return TmdbClient("token-v3", transport=transport, delay=0, sleep=lambda _: None, **kwargs)


def test_settings_tmdb_por_defecto(monkeypatch) -> None:
    for name in (
        "MEDIATECA_TMDB_API_TOKEN",
        "MEDIATECA_TMDB_LANGUAGE",
        "MEDIATECA_TMDB_DELAY",
        "MEDIATECA_TMDB_TIMEOUT",
        "MEDIATECA_TMDB_MAX_RETRIES",
    ):
        monkeypatch.delenv(name, raising=False)
    config = Settings(_env_file=None)
    assert config.tmdb_api_token is None
    assert config.tmdb_language == "es-ES"
    assert config.tmdb_delay == 0.25
    assert config.tmdb_timeout == 10.0
    assert config.tmdb_max_retries == 3


def test_api_key_v3_se_envia_como_parametro() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    with _client(handler) as client:
        client.search_movie("cine", year=2020)

    assert requests
    assert requests[0].url.params["api_key"] == "token-v3"
    assert requests[0].url.params["language"] == "es-ES"
    assert requests[0].url.params["year"] == "2020"
    assert "authorization" not in requests[0].headers


def test_read_access_token_v4_se_envia_como_bearer() -> None:
    token = "eyJhbGciOiJIUzI1NiJ9.payload.signature"
    assert is_jwt_token(token)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    transport = httpx.MockTransport(handler)
    with TmdbClient(token, transport=transport, delay=0, sleep=lambda _: None) as client:
        client.search_movie("cine")

    assert requests[0].headers["authorization"] == f"Bearer {token}"
    assert "api_key" not in requests[0].url.params


def test_search_movie_parsea_resultados() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 1,
                        "title": "Película",
                        "original_title": "Movie",
                        "release_date": "2023-05-01",
                        "popularity": 12.5,
                        "origin_country": ["ES"],
                    }
                ]
            },
        )

    with _client(handler) as client:
        results = client.search_movie("pelicula", year=2023)

    assert len(results) == 1
    assert results[0].id == 1
    assert results[0].title == "Película"
    assert results[0].original_title == "Movie"
    assert results[0].release_date == "2023-05-01"
    assert results[0].popularity == 12.5
    assert results[0].origin_country == ["ES"]


def test_get_movie_parsea_paises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": 7,
                "title": "Película",
                "original_title": "Movie",
                "release_date": "2023-05-01",
                "production_countries": [
                    {"iso_3166_1": "ES", "name": "Spain"},
                    {"iso_3166_1": "FR", "name": "France"},
                ],
                "origin_country": ["ES"],
            },
        )

    with _client(handler) as client:
        detail = client.get_movie(7)

    assert detail.id == 7
    assert detail.production_countries == ["ES", "FR"]
    assert detail.origin_country == ["ES"]


def test_reintenta_error_temporal() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, json={})
        return httpx.Response(200, json={"results": []})

    with _client(handler) as client:
        client.search_movie("cine")

    assert calls == 2


def test_no_reintenta_error_de_autenticacion() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={})

    with _client(handler) as client:
        with pytest.raises(TmdbAuthError):
            client.search_movie("cine")

    assert calls == 1


def test_respeta_retry_after() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={})
        return httpx.Response(200, json={"results": []})

    transport = httpx.MockTransport(handler)
    with TmdbClient(
        "token-v3",
        transport=transport,
        delay=0,
        max_retries=3,
        sleep=sleeps.append,
    ) as client:
        client.search_movie("cine")

    assert calls == 2
    assert 2.0 in sleeps


def test_reintenta_timeout() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.TimeoutException("timeout")
        return httpx.Response(200, json={"results": []})

    with _client(handler) as client:
        client.search_movie("cine")

    assert calls == 2


def test_normalizacion_y_candidatos_de_titulo() -> None:
    assert normalize_title("20.000 especies de abejas / ") == "20 000 especies de abejas"
    assert normalize_title("  Amélie  ") == "amelie"
    assert title_candidates("20.000 especies de abejas / ", "20.000 especies de abejas") == [
        "20.000 especies de abejas"
    ]
    assert title_candidates(None, "Título original / Título traducido") == [
        "Título original / Título traducido",
        "Título original",
    ]


def _result(
    movie_id: int,
    title: str,
    year: str,
    *,
    original_title: str | None = None,
    popularity: float = 0,
) -> TmdbSearchResult:
    return TmdbSearchResult(
        id=movie_id,
        title=title,
        original_title=original_title or title,
        release_date=f"{year}-01-01",
        popularity=popularity,
    )


def test_emparejamiento_con_tolerancia_de_anio() -> None:
    results = [_result(1, "Película", "2022"), _result(2, "Película", "2025")]
    match = select_best_match(["Pelicula"], results, 2023)
    assert match is not None
    assert match.id == 1


def test_emparejamiento_rechaza_anio_distinto() -> None:
    results = [_result(1, "Película", "1999")]
    assert select_best_match(["Pelicula"], results, 2023) is None


def test_emparejamiento_sin_anio_exige_titulo_exacto() -> None:
    results = [_result(1, "Película", "2020")]
    assert select_best_match(["Pelicula"], results, None) is not None
    assert select_best_match(["Peli"], results, None) is None


def test_emparejamiento_elige_el_mejor_y_desempata_por_popularidad() -> None:
    results = [
        _result(1, "Otra pelicula", "2023", popularity=100),
        _result(2, "Pelicula", "2023", popularity=1),
        _result(3, "Pelicula", "2023", popularity=10),
    ]
    match = select_best_match(["Pelicula"], results, 2023)
    assert match is not None
    assert match.id == 3


def test_resolucion_de_paises() -> None:
    detail = TmdbMovieDetail(
        id=1,
        title="Pelicula",
        original_title="Movie",
        release_date="2023-01-01",
        production_countries=["es", "FR", "es"],
        origin_country=["US"],
    )
    assert resolve_countries(detail) == ["ES", "FR"]
    assert resolve_countries(
        TmdbMovieDetail(1, "Pelicula", "Movie", "2023-01-01", [], ["US"])
    ) == ["US"]
    assert resolve_countries(
        TmdbMovieDetail(1, "Pelicula", "Movie", "2023-01-01", [], [])
    ) == []


def test_find_movie_busca_candidatos_y_obtiene_detalle() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/3/search/movie":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 10,
                            "title": "20.000 especies de abejas",
                            "original_title": "20.000 especies de abejas",
                            "release_date": "2023-01-01",
                            "popularity": 1,
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "id": 10,
                "title": "20.000 especies de abejas",
                "original_title": "20.000 especies de abejas",
                "release_date": "2023-01-01",
                "production_countries": [{"iso_3166_1": "ES"}],
            },
        )

    with _client(handler) as client:
        found = find_movie(
            client,
            titulo_uniforme=None,
            titulo="20.000 especies de abejas / ",
            anio=2023,
        )

    assert found is not None
    match, detail = found
    assert match.id == 10
    assert resolve_countries(detail) == ["ES"]
    assert calls == ["/3/search/movie", "/3/movie/10"]


def test_configure_logging_silencia_httpx() -> None:
    from mediateca.core.logging import configure_logging

    configure_logging()

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_api_key_v3_no_aparece_en_logs(caplog) -> None:
    from mediateca.core.logging import configure_logging

    configure_logging()
    caplog.set_level(logging.INFO)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    with _client(handler) as client:
        client.search_movie("cine")

    assert "token-v3" not in caplog.text

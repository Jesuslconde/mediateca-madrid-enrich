from __future__ import annotations

import json
from urllib.parse import urlencode

import httpx
import pytest

from mediateca.catalog.flaresolverr import (
    FlareSolverrClient,
    FlareSolverrCookie,
    FlareSolverrError,
)


def _client(handler) -> tuple[FlareSolverrClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return FlareSolverrClient("http://flare:8191/", http_client=http_client), http_client


def test_peticion_get_envia_parametros_y_devuelve_solucion() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "message": "ok",
                "solution": {
                    "status": 200,
                    "url": "https://opac.example/final",
                    "response": "<html>resuelto</html>",
                    "cookies": [
                        {
                            "name": "sid",
                            "value": "abc",
                            "domain": ".opac.example",
                            "path": "/",
                        }
                    ],
                    "userAgent": "FlareSolverr/1.0",
                },
            },
        )

    client, http_client = _client(handler)
    try:
        response = client.request(
            "GET",
            "https://opac.example/buscar",
            params={"ACC": 101, "q": "cine"},
        )
    finally:
        client.close()
        http_client.close()

    target = httpx.URL(seen["url"])
    assert seen["cmd"] == "request.get"
    assert seen["maxTimeout"] == 60000
    assert target.params["ACC"] == "101"
    assert target.params["q"] == "cine"
    assert response.status_code == 200
    assert response.text == "<html>resuelto</html>"
    assert response.url == "https://opac.example/final"
    assert response.user_agent == "FlareSolverr/1.0"
    assert response.cookies == [
        FlareSolverrCookie(
            name="sid", value="abc", domain=".opac.example", path="/"
        )
    ]


def test_peticion_post_envia_formulario_y_cookies() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "solution": {
                    "status": 200,
                    "url": "https://opac.example/buscar",
                    "response": "<html>ok</html>",
                },
            },
        )

    client, http_client = _client(handler)
    try:
        response = client.request(
            "POST",
            "https://opac.example/buscar",
            data={"ACC": "131", "xsqf01": "cine"},
            cookies=[
                FlareSolverrCookie(
                    name="sid", value="abc", domain=".opac.example", path="/"
                )
            ],
        )
    finally:
        client.close()
        http_client.close()

    assert seen["cmd"] == "request.post"
    assert seen["postData"] == urlencode({"ACC": "131", "xsqf01": "cine"})
    assert seen["cookies"] == [
        {"name": "sid", "value": "abc", "domain": ".opac.example", "path": "/"}
    ]
    assert response.text == "<html>ok</html>"


def test_rechaza_metodos_no_soportados() -> None:
    client, http_client = _client(lambda request: httpx.Response(200))
    try:
        with pytest.raises(FlareSolverrError, match="PUT"):
            client.request("PUT", "https://opac.example")
    finally:
        client.close()
        http_client.close()


@pytest.mark.parametrize(
    "body",
    [
        {"status": "error", "message": "error simulado"},
        {"status": "ok"},
        {"status": "ok", "solution": {"status": 200}},
        {"status": "ok", "solution": {"status": "no-numerico", "response": "x"}},
        ["lista"],
    ],
)
def test_valida_respuestas_incompletas_o_con_error(body) -> None:
    client, http_client = _client(
        lambda request: httpx.Response(200, json=body)
    )
    try:
        with pytest.raises(FlareSolverrError) as excinfo:
            client.request(
                "GET",
                "https://opac.example",
                cookies=[FlareSolverrCookie("sid", "secreto")],
            )
    finally:
        client.close()
        http_client.close()

    assert "secreto" not in str(excinfo.value)


def test_envuelve_errores_http_y_timeouts() -> None:
    client, http_client = _client(
        lambda request: httpx.Response(503, text="no disponible")
    )
    try:
        with pytest.raises(FlareSolverrError, match="No se pudo contactar"):
            client.request("GET", "https://opac.example")
    finally:
        client.close()
        http_client.close()

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    client, http_client = _client(timeout_handler)
    try:
        with pytest.raises(FlareSolverrError, match="no respondio a tiempo"):
            client.request("GET", "https://opac.example")
    finally:
        client.close()
        http_client.close()

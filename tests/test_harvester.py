from __future__ import annotations

import httpx
import pytest
from mediateca_shared.models import Edicion, HarvestJob
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mediateca.catalog.flaresolverr import (
    FlareSolverrCookie,
    FlareSolverrError,
    FlareSolverrResponse,
)
from mediateca.catalog.harvester import (
    CaptchaRequired,
    Harvester,
    OpacClient,
    SearchItem,
    SearchPage,
    SessionExpired,
)
from mediateca.core.db import Base


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class _FakePaginationClient(OpacClient):
    def __init__(self, pages, *, expire: bool = False) -> None:
        super().__init__(delay=0)
        self.session_id = "TEST"
        self._pages = pages
        self._expire = expire
        self._expired = False
        self.searches = 0
        self.requested: list[str] = []

    def search(self, query: str) -> SearchPage:
        self.searches += 1
        return self._pages[0]

    def fetch_search_page(
        self, url: str, query: str, *, recover_session: bool = True
    ) -> SearchPage:
        self.requested.append(url)
        if self._expire and url == "expire" and not self._expired:
            self._expired = True
            raise SessionExpired("sesion caducada")
        return self._pages[1]

    def open_session(self) -> str:
        return "TEST"

    def _doc_page_url(self, doc: int) -> str:
        return f"doc:{doc}"


def _page(*, next_url: str | None, doc: int, html: str = "") -> SearchPage:
    return SearchPage(
        query="*",
        total=3,
        items=[SearchItem(doc=doc, url=f"detail:{doc}")],
        next_url=next_url,
        html=html,
    )


def test_search_all_recorre_varias_paginas() -> None:
    client = _FakePaginationClient(
        [_page(next_url="next", doc=1), _page(next_url=None, doc=2)]
    )

    pages = list(client.search_all("*"))

    assert [page.items[0].doc for page in pages] == [1, 2]
    assert client.requested == ["next"]


def test_search_all_recupera_sesion_con_rebusqueda_y_salto() -> None:
    client = _FakePaginationClient(
        [_page(next_url="expire", doc=1), _page(next_url=None, doc=2)],
        expire=True,
    )

    pages = list(client.search_all("*"))

    assert [page.items[0].doc for page in pages] == [1, 2]
    assert client.searches == 2
    assert client.requested == ["expire", "doc:2"]


class _PageFeedClient:
    def __init__(self, pages: list[SearchPage]) -> None:
        self.delay = 0.0
        self.pages = pages
        self.calls: list[tuple[str, int | None, int | None]] = []

    def search_all(
        self,
        query: str,
        *,
        max_pages: int | None = None,
        start_doc: int | None = None,
    ):
        self.calls.append((query, max_pages, start_doc))
        yield from self.pages


def _search_html(entries: list[tuple[int, str, str]]) -> str:
    items = []
    for doc, titn, titulo in entries:
        items.append(
            f"""
            <li class="c-docs_unit">
              <a class="c-docs_title" href="?ACC=165&amp;DOC={doc}&amp;TITN={titn}">
                {titulo}
              </a>
              <p class="c-docs_marc">
                <span class="js-TITN">{titn}</span>
                <span class="js-T245a">{titulo}</span>
                <span class="js-FEPU">2024</span>
                <span class="js-LENG">spa</span>
                <span class="js-T300a">1 DVD-Video (ca. 90 min) : son., col.</span>
              </p>
            </li>
            """
        )
    return f"<html><body><ul>{''.join(items)}</ul></body></html>"


def test_harvest_discovery_guarda_checkpoint_y_reanuda_sin_duplicar(
    search_results_fixture,
) -> None:
    session = _session()
    html = search_results_fixture.read_text(encoding="utf-8")

    first_client = _PageFeedClient([_page(next_url=None, doc=3, html=html)])
    stats = Harvester(session, client=first_client).harvest_discovery(max_pages=1)

    assert stats["processed"] == 3
    assert session.scalar(select(func.count(Edicion.id))) == 3
    job = session.scalars(select(HarvestJob).order_by(HarvestJob.id.desc())).first()
    assert job is not None
    assert job.cursor_doc == 3
    assert job.cursor_titn == "2109999"
    assert job.status == "completed"

    resume_html = _search_html(
        [
            (3, "2109999", "Cine experimental en VHS"),
            (4, "2110000", "Novedad del catalogo"),
        ]
    )
    second_client = _PageFeedClient([_page(next_url=None, doc=4, html=resume_html)])
    stats = Harvester(session, client=second_client).harvest_discovery(
        cursor_doc=job.cursor_doc,
        cursor_titn=job.cursor_titn,
        max_pages=1,
    )

    assert second_client.calls == [("*", 1, 3)]
    assert stats["processed"] == 1
    assert session.scalar(select(func.count(Edicion.id))) == 4
    nuevo = session.scalars(select(Edicion).where(Edicion.titn == "2110000")).one()
    assert nuevo.discovery_seen_at is not None
    assert nuevo.missing_at is None


class _FakeSolver:
    def __init__(
        self,
        response: FlareSolverrResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def request(self, method, url, *, params=None, data=None, cookies=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "data": data,
                "cookies": cookies,
            }
        )
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _captcha_client(
    solver: _FakeSolver, *, url: str = "http://flare:8191"
) -> OpacClient:
    client = OpacClient(
        delay=0,
        flaresolverr_url=url,
        flaresolverr_client=solver,
    )
    previous = client.client
    client.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="No soy un robot")
        )
    )
    previous.close()
    return client


def test_opac_client_configura_flaresolverr() -> None:
    client = OpacClient(
        delay=0,
        flaresolverr_url="http://flare:8191",
        flaresolverr_max_timeout_ms=1234,
    )
    try:
        assert client.flaresolverr_url == "http://flare:8191"
        assert client.flaresolverr_max_timeout_ms == 1234
        assert client.captchas == 0
        assert client.captchas_solved == 0
        assert client.captchas_failed == 0
    finally:
        client.close()


def test_resuelve_captcha_get_y_sincroniza_cookies() -> None:
    solver = _FakeSolver(
        FlareSolverrResponse(
            status_code=200,
            text="<html>ficha resuelta</html>",
            url="https://opac.example/final",
            cookies=[
                FlareSolverrCookie(
                    name="sid", value="nuevo", domain="opac.example", path="/"
                )
            ],
            user_agent="FlareSolverr/UA",
        )
    )
    client = _captcha_client(solver)
    client.client.cookies.set("previa", "1", domain="opac.example", path="/")
    try:
        response = client._request(
            "GET", "https://opac.example/buscar", params={"ACC": 101}
        )
        cookies = {cookie.name: cookie.value for cookie in client.client.cookies.jar}
        user_agent = client.client.headers["User-Agent"]
        metrics = {
            "captchas": client.captchas,
            "resueltos": client.captchas_solved,
            "fallidos": client.captchas_failed,
        }
    finally:
        client.close()

    assert response.text == "<html>ficha resuelta</html>"
    assert str(response.url) == "https://opac.example/final"
    assert solver.calls[0]["method"] == "GET"
    assert solver.calls[0]["params"] == {"ACC": 101}
    assert solver.calls[0]["cookies"][0].name == "previa"
    assert cookies["sid"] == "nuevo"
    assert user_agent == "FlareSolverr/UA"
    assert metrics == {"captchas": 1, "resueltos": 1, "fallidos": 0}


def test_resuelve_captcha_post_conservando_el_formulario() -> None:
    solver = _FakeSolver(
        FlareSolverrResponse(
            status_code=200,
            text="<html>busqueda resuelta</html>",
            url="https://opac.example/buscar",
        )
    )
    client = _captcha_client(solver)
    try:
        response = client._request(
            "POST",
            "https://opac.example/buscar",
            data={"ACC": "131", "xsqf01": "cine"},
        )
    finally:
        client.close()

    assert response.text == "<html>busqueda resuelta</html>"
    assert solver.calls[0]["method"] == "POST"
    assert solver.calls[0]["data"] == {"ACC": "131", "xsqf01": "cine"}
    assert client.captchas_solved == 1


def test_sin_url_de_flaresolverr_el_captcha_falla(monkeypatch) -> None:
    from mediateca.core.config import settings

    monkeypatch.setattr(settings, "flaresolverr_url", None)
    solver = _FakeSolver()
    client = _captcha_client(solver, url="")
    try:
        with pytest.raises(CaptchaRequired):
            client._request("GET", "https://opac.example/buscar")
    finally:
        client.close()

    assert solver.calls == []
    assert client.captchas == 1
    assert client.captchas_solved == 0
    assert client.captchas_failed == 1


def test_error_de_flaresolverr_falla_sin_bucle() -> None:
    solver = _FakeSolver(error=FlareSolverrError("no disponible"))
    client = _captcha_client(solver)
    try:
        with pytest.raises(CaptchaRequired):
            client._request("GET", "https://opac.example/buscar")
    finally:
        client.close()

    assert len(solver.calls) == 1
    assert client.captchas == 1
    assert client.captchas_solved == 0
    assert client.captchas_failed == 1


def test_respuesta_de_flaresolverr_que_sigue_siendo_captcha() -> None:
    solver = _FakeSolver(
        FlareSolverrResponse(
            status_code=200,
            text="No soy un robot",
            url="https://opac.example/buscar",
        )
    )
    client = _captcha_client(solver)
    try:
        with pytest.raises(CaptchaRequired):
            client._request("GET", "https://opac.example/buscar")
    finally:
        client.close()

    assert len(solver.calls) == 1
    assert client.captchas == 1
    assert client.captchas_solved == 0
    assert client.captchas_failed == 1

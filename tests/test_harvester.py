from __future__ import annotations

from mediateca_shared.models import Edicion, HarvestJob
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mediateca.catalog.harvester import (
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

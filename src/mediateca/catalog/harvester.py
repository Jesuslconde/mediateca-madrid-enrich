from __future__ import annotations

import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from mediateca_shared.models import HarvestJob, HarvestRun
from sqlalchemy.orm import Session

from mediateca.catalog.flaresolverr import (
    FlareSolverrClient,
    FlareSolverrCookie,
    FlareSolverrError,
)
from mediateca.catalog.jobs import create_job, finish_job, update_cursor
from mediateca.catalog.parser import parse_detail, parse_search_results
from mediateca.catalog.repository import (
    mark_absent_since,
    select_pending_titns,
    upsert_edicion,
    upsert_stub,
)
from mediateca.core.config import settings
from mediateca.core.logging import get_logger

logger = get_logger(__name__)

BASE_OPAC = settings.opac_base_url.rstrip("/") + settings.opac_path
SESSION_RE = re.compile(r"/abnetopac/([A-Za-z0-9]+)")
DOC_RE = re.compile(r"ACC=165(?:&amp;|&)DOC=(\d+)")
NEXT_RE = re.compile(r"ACC=161(?:&amp;|&)DOC=(\d+)")
TOTAL_RE = re.compile(r"\(([\d.]+)\s*Registros\)")


class OpacError(RuntimeError):
    pass


class SessionExpired(OpacError):
    pass


class CaptchaRequired(OpacError):
    pass


@dataclass(slots=True)
class SearchItem:
    doc: int
    url: str
    titulo: str | None = None


@dataclass(slots=True)
class SearchPage:
    query: str
    total: int
    items: list[SearchItem] = field(default_factory=list)
    next_url: str | None = None
    html: str = ""


class OpacClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        path: str | None = None,
        timeout: float | None = None,
        delay: float | None = None,
        max_retries: int | None = None,
        user_agent: str | None = None,
        flaresolverr_url: str | None = None,
        flaresolverr_max_timeout_ms: int | None = None,
        flaresolverr_client: FlareSolverrClient | None = None,
    ) -> None:
        self.base_url = (base_url or settings.opac_base_url).rstrip("/")
        self.path = path or settings.opac_path
        self.timeout = timeout or settings.crawl_timeout
        self.delay = delay if delay is not None else settings.crawl_delay
        self.max_retries = max_retries or settings.crawl_max_retries
        self.user_agent = user_agent or settings.user_agent
        self.client = httpx.Client(
            follow_redirects=True,
            timeout=self.timeout,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Language": "es-ES,es;q=0.9",
            },
        )
        self.session_id: str | None = None
        self.captchas = 0
        self.captchas_solved = 0
        self.captchas_failed = 0
        self.session_renewals = 0
        self.flaresolverr_url = (flaresolverr_url or settings.flaresolverr_url) or None
        self.flaresolverr_max_timeout_ms = (
            flaresolverr_max_timeout_ms
            if flaresolverr_max_timeout_ms is not None
            else settings.flaresolverr_max_timeout_ms
        )
        self.flaresolverr_client = flaresolverr_client
        self._flaresolverr: FlareSolverrClient | None = flaresolverr_client

    def close(self) -> None:
        self.client.close()
        if self._flaresolverr is not None and self._flaresolverr is not self.flaresolverr_client:
            self._flaresolverr.close()

    def _get_flaresolverr(self) -> FlareSolverrClient | None:
        if not self.flaresolverr_url:
            return None
        if self._flaresolverr is None:
            self._flaresolverr = FlareSolverrClient(
                self.flaresolverr_url,
                max_timeout_ms=self.flaresolverr_max_timeout_ms,
            )
        return self._flaresolverr

    def __enter__(self) -> OpacClient:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    @property
    def opac_url(self) -> str:
        return self.base_url + self.path

    def _extract_session(self, response: httpx.Response) -> str | None:
        for candidate in (str(response.url), response.text):
            match = SESSION_RE.search(candidate)
            if match:
                return match.group(1)
        match = re.search(r"URL=([^\"']+)", response.text)
        if match:
            redirected = SESSION_RE.search(match.group(1))
            if redirected:
                return redirected.group(1)
        return None

    def open_session(self) -> str:
        if self.session_id is not None:
            self.session_renewals += 1
        response = self.client.get(self.opac_url, params={"ACC": 101})
        response.raise_for_status()
        session_id = self._extract_session(response)
        if not session_id:
            raise OpacError("No se ha podido obtener el identificador de sesion del OPAC")
        self.session_id = session_id
        # Una segunda peticion inicializa las cookies y el estado de la sesion.
        initialized = self.client.get(f"{self.opac_url}/{session_id}", params={"ACC": 101})
        initialized.raise_for_status()
        return session_id

    def _ensure_session(self) -> str:
        if not self.session_id:
            return self.open_session()
        return self.session_id

    def _url(self, nt: int = 1) -> str:
        session_id = self._ensure_session()
        return f"{self.opac_url}/{session_id}/NT{nt}"

    def _rebind_session(self, url: str) -> str:
        if not self.session_id:
            return url
        return SESSION_RE.sub(f"/abnetopac/{self.session_id}", url, count=1)

    def _check_response(
        self, response: httpx.Response, *, count_captcha: bool = True
    ) -> None:
        text = response.text
        if "No soy un robot" in text or "chequeado 'No soy un robot'" in text:
            if count_captcha:
                self.captchas += 1
            raise CaptchaRequired(
                "El OPAC ha solicitado un reCAPTCHA; se detiene la recoleccion"
            )
        if "timeout.htm" in text or "Sesión expirada" in text:
            raise SessionExpired("La sesion del OPAC ha caducado")

    def _request(
        self, method: str, url: str, *, recover_session: bool = True, **kwargs
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.request(method, url, **kwargs)
                self._check_response(response)
                response.raise_for_status()
                return response
            except SessionExpired:
                if not recover_session:
                    raise
                logger.info("Sesion caducada; renovando")
                self.open_session()
                url = self._rebind_session(url)
                last_error = None
                continue
            except CaptchaRequired:
                if not self.flaresolverr_url:
                    self.captchas_failed += 1
                    raise
                try:
                    return self._solve_captcha(method, url, kwargs)
                except SessionExpired:
                    if not recover_session:
                        raise
                    logger.info(
                        "Sesion caducada durante la resolucion del captcha; renovando"
                    )
                    self.open_session()
                    url = self._rebind_session(url)
                    last_error = None
                    continue
                except CaptchaRequired:
                    raise
                except (httpx.HTTPError, OpacError) as exc:
                    last_error = exc
                    wait = self.delay * (2**attempt)
                    logger.warning(
                        "Error tras resolver el captcha (%s); reintento en %.1fs",
                        exc,
                        wait,
                    )
                    time.sleep(wait)
            except (httpx.HTTPError, OpacError) as exc:
                last_error = exc
                wait = self.delay * (2**attempt)
                logger.warning("Error de OPAC (%s); reintento en %.1fs", exc, wait)
                time.sleep(wait)

        raise OpacError(f"No se pudo completar la peticion a {url}") from last_error

    def _solve_captcha(
        self, method: str, url: str, kwargs: dict
    ) -> httpx.Response:
        solver = self._get_flaresolverr()
        if solver is None:
            raise CaptchaRequired(
                "El OPAC ha solicitado un reCAPTCHA y no hay FlareSolverr configurado"
            )

        cookies = [
            FlareSolverrCookie(
                name=cookie.name,
                value=cookie.value,
                domain=cookie.domain,
                path=cookie.path,
            )
            for cookie in self.client.cookies.jar
        ]

        try:
            solved = solver.request(
                method,
                url,
                params=kwargs.get("params"),
                data=kwargs.get("data"),
                cookies=cookies,
            )
        except FlareSolverrError as exc:
            self.captchas_failed += 1
            logger.warning("FlareSolverr no pudo resolver el captcha: %s", exc)
            raise CaptchaRequired(
                "El OPAC ha solicitado un reCAPTCHA y FlareSolverr no pudo resolverlo"
            ) from exc

        final_url = solved.url or url
        response = httpx.Response(
            solved.status_code,
            text=solved.text,
            request=httpx.Request(method, final_url),
        )

        host = httpx.URL(final_url).host or ""
        for cookie in solved.cookies:
            self.client.cookies.set(
                cookie.name,
                cookie.value,
                domain=cookie.domain or host,
                path=cookie.path or "/",
            )
        if solved.user_agent:
            self.user_agent = solved.user_agent
            self.client.headers["User-Agent"] = solved.user_agent

        try:
            self._check_response(response, count_captcha=False)
        except CaptchaRequired as exc:
            self.captchas_failed += 1
            logger.warning("FlareSolverr devolvio otra pagina de captcha")
            raise CaptchaRequired(
                "El OPAC ha solicitado un reCAPTCHA y FlareSolverr no lo ha resuelto"
            ) from exc

        response.raise_for_status()
        self.captchas_solved += 1
        return response

    def _parse_results(self, response: httpx.Response, query: str) -> SearchPage:
        soup = BeautifulSoup(response.text, "lxml")
        text = soup.get_text(" ", strip=True)
        total_match = TOTAL_RE.search(text)
        total = int(total_match.group(1).replace(".", "")) if total_match else 0

        items: list[SearchItem] = []
        seen_docs: set[int] = set()
        for anchor in soup.select('a[href*="ACC=165"]'):
            href = anchor.get("href")
            if not href:
                continue
            match = DOC_RE.search(href)
            if not match:
                continue
            doc = int(match.group(1))
            if doc in seen_docs:
                continue
            seen_docs.add(doc)
            title = anchor.get_text(" ", strip=True) or None
            items.append(
                SearchItem(
                    doc=doc,
                    url=urljoin(str(response.url), href),
                    titulo=title,
                )
            )

        next_url = None
        next_candidates: list[tuple[int, str]] = []
        for anchor in soup.select('a[href*="ACC=161"]'):
            href = anchor.get("href")
            if not href:
                continue
            match = NEXT_RE.search(href)
            if not match:
                continue
            next_candidates.append((int(match.group(1)), urljoin(str(response.url), href)))
        if next_candidates:
            max_current = max(seen_docs) if seen_docs else 0
            candidates = [item for item in next_candidates if item[0] > max_current]
            if candidates:
                next_url = min(candidates, key=lambda item: item[0])[1]

        return SearchPage(
            query=query,
            total=total,
            items=items,
            next_url=next_url,
            html=response.text,
        )

    def search(self, query: str) -> SearchPage:
        self._ensure_session()
        data = {
            "ACC": "131",
            "START": "1",
            "FORM": "2",
            "xindex": "",
            "xindty": "",
            "xindbt": "",
            "xexact": "",
            "xsqf01": query,
            "select03": "6",
            "subcat": "/",
        }
        response = self._request("POST", self._url(1), data=data)
        return self._parse_results(response, query)

    def fetch_search_page(
        self, url: str, query: str, *, recover_session: bool = True
    ) -> SearchPage:
        response = self._request("GET", url, recover_session=recover_session)
        return self._parse_results(response, query)

    def _doc_page_url(self, doc: int) -> str:
        return f"{self._url(1)}?ACC=161&DOC={int(doc)}"

    def _recover_search_page(self, query: str, doc: int | None) -> SearchPage:
        self.open_session()
        self.search(query)
        if doc is None:
            return self.fetch_search_page(self._url(1), query, recover_session=False)
        return self.fetch_search_page(
            self._doc_page_url(doc), query, recover_session=False
        )

    def search_all(
        self,
        query: str = "*",
        *,
        max_pages: int | None = None,
        start_doc: int | None = None,
    ) -> Iterator[SearchPage]:
        """Recorre la paginacion profunda y recupera la sesion si caduca."""
        page = self.search(query)
        if start_doc is not None:
            if not page.items or start_doc > page.items[-1].doc:
                page = self.fetch_search_page(
                    self._doc_page_url(start_doc), query, recover_session=False
                )
            else:
                page.items = [item for item in page.items if item.doc >= start_doc]

        pages = 0
        while page is not None:
            yield page
            pages += 1
            if max_pages is not None and pages >= max_pages:
                break
            if not page.next_url:
                break

            last_doc = page.items[-1].doc if page.items else start_doc
            try:
                page = self.fetch_search_page(
                    page.next_url, query, recover_session=False
                )
            except SessionExpired:
                logger.info(
                    "Sesion caducada durante la paginacion; re-buscando y saltando a DOC=%s",
                    last_doc,
                )
                next_doc = last_doc + 1 if last_doc is not None else None
                page = self._recover_search_page(query, next_doc)

    def fetch_detail(self, url: str) -> tuple[str, str]:
        response = self._request("GET", url)
        return response.text, str(response.url)

    def fetch_by_titn(self, titn: str) -> tuple[str, str]:
        response = self._request(
            "GET", self._url(1), params={"TITN": titn, "FORM": "1"}
        )
        return response.text, str(response.url)


class Harvester:
    def __init__(
        self,
        session: Session,
        *,
        client: OpacClient | None = None,
    ) -> None:
        self.session = session
        self.client = client or OpacClient()

    def _save(self, parsed):
        edicion = upsert_edicion(self.session, parsed)
        self.session.commit()
        return edicion

    def _opac_metrics(self) -> dict[str, int]:
        return {
            "captchas": int(getattr(self.client, "captchas", 0)),
            "captchas_solved": int(getattr(self.client, "captchas_solved", 0)),
            "captchas_failed": int(getattr(self.client, "captchas_failed", 0)),
            "session_renewals": int(getattr(self.client, "session_renewals", 0)),
        }

    def harvest_query(
        self,
        query: str,
        *,
        max_pages: int = 1,
        limit: int | None = None,
        delay: float | None = None,
    ) -> dict[str, int]:
        delay = self.client.delay if delay is None else delay
        run = HarvestRun(kind="harvest", query=query, status="running")
        self.session.add(run)
        self.session.commit()

        processed = 0
        errors = 0
        try:
            page = self.client.search(query)
            pages = 0
            while page and pages < max_pages:
                for item in page.items:
                    if limit is not None and processed >= limit:
                        break
                    try:
                        html, final_url = self.client.fetch_detail(item.url)
                        parsed = parse_detail(html, final_url)
                        self._save(parsed)
                        processed += 1
                        logger.info("Ficha %s guardada (%s)", parsed.titn, parsed.titulo)
                    except Exception as exc:  # noqa: BLE001
                        self.session.rollback()
                        errors += 1
                        logger.exception("Error procesando %s: %s", item.url, exc)
                    time.sleep(delay)
                if limit is not None and processed >= limit:
                    break
                pages += 1
                if not page.next_url:
                    break
                page = self.client.fetch_search_page(page.next_url, query)

            stats = {
                "processed": processed,
                "errors": errors,
                "pages": pages,
                **self._opac_metrics(),
            }
            run.status = "finished"
            run.stats = stats
            return stats
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error = str(exc)
            raise
        finally:
            run.finished_at = datetime.now(UTC)
            self.session.commit()

    def _enrich_titn(self, titn: str, *, delay: float) -> None:
        attempts = max(
            1, int(getattr(self.client, "max_retries", settings.crawl_max_retries))
        )
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                html, final_url = self.client.fetch_by_titn(titn)
                parsed = parse_detail(html, final_url)
                self._save(parsed)
                return
            except CaptchaRequired:
                self.session.rollback()
                raise
            except Exception as exc:  # noqa: BLE001
                self.session.rollback()
                last_error = exc
                wait = delay * (2**attempt)
                logger.warning(
                    "Error enriqueciendo %s (%s); reintento en %.1fs",
                    titn,
                    exc,
                    wait,
                )
                if attempt + 1 < attempts:
                    time.sleep(wait)
        raise OpacError(f"No se pudo enriquecer la ficha {titn}") from last_error

    def harvest_enrichment(
        self,
        *,
        limit: int = 5000,
        delay: float | None = None,
        cursor_titn: str | None = None,
        job: HarvestJob | None = None,
    ) -> dict[str, int | list[str] | None]:
        delay = self.client.delay if delay is None else delay
        owns_job = job is None
        if job is None:
            job = create_job(
                self.session,
                "enrich",
                batch_size=limit,
                cursor_titn=cursor_titn,
            )
        else:
            cursor_titn = cursor_titn if cursor_titn is not None else job.cursor_titn
            limit = job.batch_size or limit
        self.session.commit()

        run = HarvestRun(kind="enrich", query=None, status="running")
        self.session.add(run)
        self.session.commit()

        processed = errors = 0
        failed: list[str] = []
        processed_titns: list[str] = []
        last_titn = cursor_titn
        pending: list[str] = []

        try:
            pending = select_pending_titns(
                self.session, limit=limit, after_titn=cursor_titn
            )
            for titn in pending:
                started = time.monotonic()
                try:
                    self._enrich_titn(titn, delay=delay)
                except CaptchaRequired:
                    raise
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    failed.append(titn)
                    logger.exception(
                        "Ficha fallida tras reintentos",
                        extra={
                            "job_id": job.id,
                            "job_type": job.job_type,
                            "titn": titn,
                            "result": "failed",
                            "duration_ms": round(
                                (time.monotonic() - started) * 1000, 2
                            ),
                            "error": str(exc),
                        },
                    )
                else:
                    processed += 1
                    processed_titns.append(titn)
                    logger.info(
                        "Ficha enriquecida",
                        extra={
                            "job_id": job.id,
                            "job_type": job.job_type,
                            "titn": titn,
                            "result": "enriched",
                            "duration_ms": round(
                                (time.monotonic() - started) * 1000, 2
                            ),
                        },
                    )

                last_titn = titn
                self.session.commit()
                update_cursor(
                    self.session,
                    job,
                    cursor_titn=last_titn,
                    stats={
                        "selected": len(pending),
                        "processed": processed,
                        "errors": errors,
                        "failed": failed,
                        **self._opac_metrics(),
                    },
                )
                self.session.commit()
                time.sleep(delay)

            stats = {
                "selected": len(pending),
                "processed": processed,
                "errors": errors,
                "failed": failed,
                "cursor_titn": last_titn,
                "processed_titns": processed_titns,
                **self._opac_metrics(),
            }
            run.status = "finished"
            run.stats = stats
            if owns_job:
                finish_job(self.session, job, status="completed", stats=stats)
            return stats
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error = str(exc)
            if owns_job:
                finish_job(self.session, job, status="failed", error=str(exc))
            raise
        finally:
            run.finished_at = datetime.now(UTC)
            self.session.commit()

    def harvest_discovery(
        self,
        *,
        max_pages: int | None = None,
        limit: int | None = None,
        delay: float | None = None,
        cursor_doc: int | None = None,
        cursor_titn: str | None = None,
        job: HarvestJob | None = None,
    ) -> dict[str, int]:
        delay = self.client.delay if delay is None else delay
        owns_job = job is None
        if job is None:
            job = create_job(
                self.session,
                "discover",
                cursor_doc=cursor_doc,
                cursor_titn=cursor_titn,
            )
        else:
            cursor_doc = cursor_doc if cursor_doc is not None else job.cursor_doc
            cursor_titn = cursor_titn if cursor_titn is not None else job.cursor_titn
        self.session.commit()

        started_at = datetime.now(UTC)
        run = HarvestRun(kind="discover", query="*", status="running")
        self.session.add(run)
        self.session.commit()

        seen: set[str] = set()
        processed = pages = errors = missing = 0
        resume_titn = cursor_titn if cursor_doc is not None else None
        first_page = True
        limit_reached = False
        full_run = cursor_doc is None and max_pages is None and limit is None
        last_doc = cursor_doc
        last_titn = cursor_titn

        try:
            for page in self.client.search_all(
                "*", max_pages=max_pages, start_doc=cursor_doc
            ):
                page_items = parse_search_results(page.html)
                if first_page:
                    first_page = False
                    if resume_titn and page_items:
                        if page_items[0].titn != resume_titn:
                            logger.warning(
                                "El cursor TITN %s no coincide con el primer resultado %s",
                                resume_titn,
                                page_items[0].titn,
                            )

                for parsed in page_items:
                    if resume_titn and parsed.titn == resume_titn:
                        resume_titn = None
                        continue
                    if limit is not None and processed >= limit:
                        limit_reached = True
                        break
                    started = time.monotonic()
                    try:
                        with self.session.begin_nested():
                            upsert_stub(self.session, parsed)
                    except Exception as exc:  # noqa: BLE001
                        errors += 1
                        logger.exception(
                            "Error creando stub",
                            extra={
                                "job_id": job.id,
                                "job_type": job.job_type,
                                "titn": parsed.titn,
                                "doc": parsed.doc,
                                "result": "failed",
                                "duration_ms": round(
                                    (time.monotonic() - started) * 1000, 2
                                ),
                                "error": str(exc),
                            },
                        )
                        continue

                    processed += 1
                    seen.add(parsed.titn)
                    last_titn = parsed.titn
                    if parsed.doc is not None:
                        last_doc = parsed.doc
                    logger.info(
                        "Stub creado",
                        extra={
                            "job_id": job.id,
                            "job_type": job.job_type,
                            "titn": parsed.titn,
                            "doc": parsed.doc,
                            "result": "stub",
                            "duration_ms": round(
                                (time.monotonic() - started) * 1000, 2
                            ),
                        },
                    )

                pages += 1
                self.session.commit()
                update_cursor(
                    self.session,
                    job,
                    cursor_doc=last_doc,
                    cursor_titn=last_titn,
                    stats={
                        "processed": processed,
                        "pages": pages,
                        "errors": errors,
                        **self._opac_metrics(),
                    },
                )
                self.session.commit()
                time.sleep(delay)
                if limit_reached:
                    break

            if full_run and processed > 0:
                missing = mark_absent_since(
                    self.session, seen, since=started_at
                )

            stats = {
                "processed": processed,
                "pages": pages,
                "errors": errors,
                "missing": missing,
                "processed_titns": sorted(seen),
                **self._opac_metrics(),
            }
            run.status = "finished"
            run.stats = stats
            if owns_job:
                finish_job(self.session, job, status="completed", stats=stats)
            return stats
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error = str(exc)
            if owns_job:
                finish_job(self.session, job, status="failed", error=str(exc))
            raise
        finally:
            run.finished_at = datetime.now(UTC)
            self.session.commit()

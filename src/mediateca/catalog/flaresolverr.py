from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx


class FlareSolverrError(RuntimeError):
    pass


@dataclass(slots=True)
class FlareSolverrCookie:
    name: str
    value: str
    domain: str | None = None
    path: str | None = None


@dataclass(slots=True)
class FlareSolverrResponse:
    status_code: int
    text: str
    url: str
    cookies: list[FlareSolverrCookie] = field(default_factory=list)
    user_agent: str | None = None


class FlareSolverrClient:
    def __init__(
        self,
        base_url: str,
        *,
        max_timeout_ms: int = 60000,
        timeout: float | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_timeout_ms = max_timeout_ms
        self.timeout = (
            timeout if timeout is not None else max_timeout_ms / 1000 + 15.0
        )
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=self.timeout)

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/v1"

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> FlareSolverrClient:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        cookies: list[FlareSolverrCookie] | None = None,
    ) -> FlareSolverrResponse:
        normalized_method = method.upper()
        if normalized_method not in {"GET", "POST"}:
            raise FlareSolverrError(
                f"FlareSolverr no soporta el metodo {normalized_method}"
            )

        target_url = _with_params(url, params)
        payload: dict[str, Any] = {
            "cmd": f"request.{normalized_method.lower()}",
            "url": target_url,
            "maxTimeout": self.max_timeout_ms,
        }
        if normalized_method == "POST":
            payload["postData"] = urlencode(data or {}, doseq=True)
        if cookies:
            payload["cookies"] = [
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain or "",
                    "path": cookie.path or "/",
                }
                for cookie in cookies
            ]

        try:
            response = self._client.post(self.endpoint, json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise FlareSolverrError("FlareSolverr no respondio a tiempo") from exc
        except httpx.HTTPError as exc:
            raise FlareSolverrError(
                f"No se pudo contactar con FlareSolverr: {exc}"
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise FlareSolverrError("FlareSolverr devolvio una respuesta no JSON") from exc
        if not isinstance(body, dict):
            raise FlareSolverrError("FlareSolverr devolvio una respuesta inesperada")

        status = body.get("status")
        if status != "ok":
            message = str(body.get("message") or "error desconocido")
            raise FlareSolverrError(f"FlareSolverr devolvio un error: {message}")

        solution = body.get("solution")
        if not isinstance(solution, dict):
            raise FlareSolverrError("FlareSolverr no devolvio la solucion de la pagina")

        content = solution.get("response")
        if not isinstance(content, str):
            raise FlareSolverrError("FlareSolverr no devolvio el HTML de la pagina")

        try:
            status_code = int(solution.get("status") or 200)
        except (TypeError, ValueError) as exc:
            raise FlareSolverrError(
                "FlareSolverr devolvio un estado HTTP no valido"
            ) from exc

        final_url = solution.get("url")
        if not isinstance(final_url, str) or not final_url:
            final_url = target_url

        raw_cookies = solution.get("cookies")
        cookies_out: list[FlareSolverrCookie] = []
        if isinstance(raw_cookies, list):
            for item in raw_cookies:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                value = item.get("value")
                if not isinstance(name, str) or not isinstance(value, str):
                    continue
                domain = item.get("domain")
                path = item.get("path")
                cookies_out.append(
                    FlareSolverrCookie(
                        name=name,
                        value=value,
                        domain=domain if isinstance(domain, str) else None,
                        path=path if isinstance(path, str) else None,
                    )
                )

        user_agent = solution.get("userAgent")
        return FlareSolverrResponse(
            status_code=status_code,
            text=content,
            url=final_url,
            cookies=cookies_out,
            user_agent=user_agent if isinstance(user_agent, str) else None,
        )


def _with_params(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    query = urlencode(params, doseq=True)
    separator = "&" if urlsplit(url).query else "?"
    return f"{url}{separator}{query}"

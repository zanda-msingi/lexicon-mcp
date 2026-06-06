"""Thin async HTTP client for the Lexicon Local API.

One job: faithful, well-typed access to Lexicon over HTTP. No business logic.
Endpoint shapes and quirks were learned from the live API and pinned in
docs/upstream-api-issues.md; this client encodes the load-bearing defenses.
"""

from __future__ import annotations

from typing import Any

import httpx

from .errors import LexiconAPIError, LexiconConnectionError

DEFAULT_BASE_URL = "http://localhost:48624"
DEFAULT_TIMEOUT = 30.0


class LexiconClient:
    """Async client wrapping the Lexicon Local API.

    Use as an async context manager::

        async with LexiconClient() as lex:
            data = await lex.request("GET", "/v1/playlists")
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> LexiconClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> Any:
        """Make a request and return the unwrapped `data` payload.

        Raises:
            LexiconConnectionError: the API could not be reached.
            LexiconAPIError: the API returned an error envelope or non-JSON body.
        """
        try:
            response = await self._http.request(method, path, params=params, json=json)
        except httpx.ConnectError as exc:
            raise LexiconConnectionError(
                f"Could not reach the Lexicon Local API at {self.base_url}. "
                "Is Lexicon running with the Local API enabled "
                "(Settings > Integrations > Local API)? Note it can take a few "
                "seconds to come online after the app launches."
            ) from exc
        except httpx.TransportError as exc:
            raise LexiconConnectionError(
                f"Network error talking to the Lexicon Local API at {self.base_url}: {exc}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise LexiconAPIError(
                f"Lexicon returned a non-JSON response (HTTP {response.status_code}) "
                f"for {method} {path}.",
                status_code=response.status_code,
            ) from exc

        # Error envelope: {"message": ..., "errorCode": N}
        if isinstance(payload, dict) and "errorCode" in payload:
            raise LexiconAPIError(
                payload.get("message", "Unknown Lexicon API error"),
                error_code=payload.get("errorCode"),
                status_code=response.status_code,
            )

        # Some write endpoints (POST/PATCH /v1/tag*) return the object at the top
        # level with no {"data": ...} wrapper (upstream quirk); pass those through.
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

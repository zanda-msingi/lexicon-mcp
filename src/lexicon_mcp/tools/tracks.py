"""Track tools: search_tracks, get_track."""

from __future__ import annotations

from typing import Any

from ..client import LexiconClient
from ..guardrails import assert_safe_search_filter

# Cap how many full track records we hand back by default. Search has no server
# pagination — a broad filter can match thousands — so we truncate the payload
# while still reporting the true total.
_DEFAULT_RESULT_LIMIT = 100


def _normalize_sort(sort: list[Any]) -> list[dict[str, str]]:
    """Force every sort entry to carry a `dir` key.

    A sort object missing `dir` crashes the Lexicon server
    (docs/upstream-api-issues.md). Accept "field" strings or {field[, dir]} dicts.
    """
    normalized: list[dict[str, str]] = []
    for entry in sort:
        if isinstance(entry, str):
            normalized.append({"field": entry, "dir": "asc"})
        elif isinstance(entry, dict):
            normalized.append({"field": entry["field"], "dir": entry.get("dir", "asc")})
        else:
            raise TypeError(f"Unsupported sort entry: {entry!r}")
    return normalized


async def search_tracks(
    client: LexiconClient,
    filter: dict[str, Any],
    *,
    fields: list[str] | None = None,
    sort: list[Any] | None = None,
    source: str | None = None,
    limit: int | None = _DEFAULT_RESULT_LIMIT,
) -> dict[str, Any]:
    """Search the library and return matching tracks.

    `filter` is a dict of field -> value/comparison (e.g. {"artist": "Daft Punk",
    "bpm": ">=120"}); matching is substring/contains for text. The filter is
    checked against the silent-return-all guardrail first, so an unsafe filter
    fails loudly instead of quietly returning the whole library.

    Search has no server-side pagination; `limit` truncates the returned records
    (None = no cap) while `total` always reports the real match count.
    """
    assert_safe_search_filter(filter)

    body: dict[str, Any] = {"filter": filter}
    if source is not None:
        body["source"] = source
    if fields is not None:
        body["fields"] = fields
    if sort is not None:
        body["sort"] = _normalize_sort(sort)

    # sort only works in a JSON body on GET (upstream quirk), so everything goes
    # in the body for consistency.
    data = await client.request("GET", "/v1/search/tracks", json=body)
    tracks = data.get("tracks", [])
    total = data.get("total", len(tracks))
    if limit is not None:
        tracks = tracks[:limit]
    return {"total": total, "returned": len(tracks), "tracks": tracks}


async def get_track(client: LexiconClient, track_id: int) -> dict[str, Any]:
    """Return the full record for one track via `GET /v1/track?id=`.

    Includes metadata, applied custom tags, cue points, and source-specific data.
    Raises LexiconAPIError if the track id does not exist.
    """
    data = await client.request("GET", "/v1/track", params={"id": track_id})
    return data["track"]

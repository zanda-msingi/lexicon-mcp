"""Track tools: search_tracks, get_track."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..client import LexiconClient
from ..guardrails import assert_safe_search_filter

# Cap how many full track records we hand back by default. Search has no server
# pagination — a broad filter can match thousands — so we truncate the payload
# while still reporting the true total.
_DEFAULT_RESULT_LIMIT = 100

# The fields a tagging or set-building conversation actually reads. Full records
# are ~3 KB each (Traktor blobs, cue points, tempo markers, file paths); this set
# is a few hundred bytes. Tools that return many tracks default to it.
COMPACT_TRACK_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "artist",
    "albumTitle",
    "genre",
    "comment",
    "bpm",
    "key",
    "energy",
    "year",
    "duration",
    "rating",
    "playCount",
    "tags",
)


def select_fields(track: dict[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    """Return only `fields` from a track record, in the order given.

    Missing fields are simply absent (never invented), so the result is
    faithful to what Lexicon returned.
    """
    return {f: track[f] for f in fields if f in track}


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
    (None = no cap) while `total` always reports the real match count. When
    `fields` is given, records contain exactly those fields (Lexicon otherwise
    forces `type`, `archived` and `location` into every one).
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
    if fields is not None:
        # Lexicon forces type/archived/location into every record regardless of
        # `fields`; honour what the caller asked for.
        tracks = [select_fields(t, fields) for t in tracks]
    return {"total": total, "returned": len(tracks), "tracks": tracks}


async def get_track(client: LexiconClient, track_id: int) -> dict[str, Any]:
    """Return the full record for one track via `GET /v1/track?id=`.

    Includes metadata, applied custom tags, cue points, and source-specific data.
    Raises LexiconAPIError if the track id does not exist.
    """
    data = await client.request("GET", "/v1/track", params={"id": track_id})
    return data["track"]

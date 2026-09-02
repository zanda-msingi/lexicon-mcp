"""Library-wide tools: library_info.

The Lexicon API has no summary endpoint, so these tools scan `GET /v1/tracks`
in 1000-row pages with a minimal field set. Measured live: ~10 ms per page,
so a 40k-track library is scanned in well under a second.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

from ..client import LexiconClient
from .playlists import list_playlists

# Max page size the API allows.
PAGE_SIZE = 1000

_OPEN_KEY = re.compile(r"^\d{1,2}[MD]$")
_CAMELOT = re.compile(r"^\d{1,2}[AB]$")


async def scan_tracks(
    client: LexiconClient, fields: Sequence[str]
) -> AsyncIterator[dict[str, Any]]:
    """Yield every track in the library with only `fields`, page by page."""
    offset = 0
    while True:
        data = await client.request(
            "GET",
            "/v1/tracks",
            json={"limit": PAGE_SIZE, "offset": offset, "fields": list(fields)},
        )
        page = data.get("tracks", [])
        for track in page:
            yield track
        offset += len(page)
        if not page or offset >= data.get("total", 0):
            return


async def library_info(client: LexiconClient) -> dict[str, Any]:
    """Return a compact summary of the whole library.

    - `tracks`: total and how many carry bpm, key, energy, and at least one tag.
    - `key_notation`: how many keyed tracks use Open Key (1D/6M), Camelot
      (8B/11A), or something else — so a caller knows which to filter with.
    - `playlists`: counts of folders, playlists and smartlists.
    - `tag_categories`: each with its tag count and how many tracks carry any of
      its tags.
    - `tags`: every tag with its category and track count (zero included, so
      unused vocabulary is visible).

    One pass over the library plus one read each of the tag taxonomy and the
    playlist tree. Grounds a conversation before any tagging or set-building.
    """
    total = with_bpm = with_key = with_energy = tagged = 0
    open_key = camelot = other_key = 0
    tag_counts: dict[int, int] = {}
    category_track_ids: dict[int, set[int]] = {}

    taxonomy = await client.request("GET", "/v1/tags")
    tags = taxonomy.get("tags", [])
    categories = taxonomy.get("categories", [])
    category_of = {t["id"]: t.get("categoryId") for t in tags}

    async for track in scan_tracks(client, ["id", "bpm", "key", "energy", "tags"]):
        total += 1
        if track.get("bpm"):
            with_bpm += 1
        key = track.get("key") or ""
        if key:
            with_key += 1
            if _OPEN_KEY.match(key):
                open_key += 1
            elif _CAMELOT.match(key):
                camelot += 1
            else:
                other_key += 1
        if track.get("energy"):
            with_energy += 1
        applied = track.get("tags") or []
        if applied:
            tagged += 1
        for tag_id in applied:
            tag_counts[tag_id] = tag_counts.get(tag_id, 0) + 1
            cat = category_of.get(tag_id)
            if cat is not None:
                category_track_ids.setdefault(cat, set()).add(track["id"])

    rows = await list_playlists(client)
    kinds = {"folders": 0, "playlists": 0, "smartlists": 0}
    for row in rows:
        plural = f"{row['kind']}s"
        if plural in kinds:
            kinds[plural] += 1

    label_of_category = {c["id"]: c.get("label") for c in categories}
    return {
        "tracks": {
            "total": total,
            "with_bpm": with_bpm,
            "with_key": with_key,
            "with_energy": with_energy,
            "tagged": tagged,
        },
        "key_notation": {"open_key": open_key, "camelot": camelot, "other": other_key},
        "playlists": kinds,
        "tag_categories": [
            {
                "id": c["id"],
                "label": c.get("label"),
                "tag_count": sum(1 for t in tags if t.get("categoryId") == c["id"]),
                "tracks_tagged": len(category_track_ids.get(c["id"], ())),
            }
            for c in categories
        ],
        "tags": [
            {
                "id": t["id"],
                "label": t.get("label"),
                "category": label_of_category.get(t.get("categoryId")),
                "track_count": tag_counts.get(t["id"], 0),
            }
            for t in tags
        ],
    }

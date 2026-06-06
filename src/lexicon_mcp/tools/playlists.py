"""Playlist tools: list_playlists, get_playlist_tracks."""

from __future__ import annotations

import asyncio
from typing import Any

from ..client import LexiconClient
from ..errors import LexiconAPIError
from ..guardrails import dedupe_track_ids

# Bound concurrent /v1/track fetches so a large playlist doesn't flood the API.
_FETCH_CONCURRENCY = 8


async def list_playlists(client: LexiconClient) -> list[dict[str, Any]]:
    """Return every playlist and folder as a nested tree.

    Faithful to `GET /v1/playlists`: a list whose first element is the ROOT node,
    with folders (`type:"1"`) containing child `playlists` and playlists
    (`type:"2"`) as leaves. Track membership is NOT included here (the API does
    not provide counts in the tree) — use `get_playlist_tracks` for a playlist's
    contents.
    """
    data = await client.request("GET", "/v1/playlists")
    return data["playlists"]


async def get_playlist_tracks(client: LexiconClient, playlist_id: int) -> list[dict[str, Any]]:
    """Return the full track records for a playlist, in playlist order.

    `GET /v1/playlist?id=` gives ordered `trackIds` only, so this resolves each to
    a full record via `GET /v1/track?id=`. Two real-world defenses apply:

    - duplicate `trackIds` (the API can return them for folder playlists) are
      collapsed, preserving first-seen order;
    - a track that no longer exists is skipped rather than failing the whole call,
      so a stale reference doesn't make the playlist unreadable.
    """
    data = await client.request("GET", "/v1/playlist", params={"id": playlist_id})
    track_ids = dedupe_track_ids(data["playlist"].get("trackIds") or [])
    if not track_ids:
        return []

    sem = asyncio.Semaphore(_FETCH_CONCURRENCY)

    async def fetch(track_id: int) -> dict[str, Any]:
        async with sem:
            track = await client.request("GET", "/v1/track", params={"id": track_id})
            return track["track"]

    results = await asyncio.gather(*(fetch(tid) for tid in track_ids), return_exceptions=True)

    tracks: list[dict[str, Any]] = []
    for result in results:  # gather preserves input order
        if isinstance(result, LexiconAPIError):
            continue  # track no longer exists; skip it
        if isinstance(result, BaseException):
            raise result  # connection/unknown errors are real failures
        tracks.append(result)
    return tracks

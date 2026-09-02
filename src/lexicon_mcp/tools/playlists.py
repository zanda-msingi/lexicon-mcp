"""Playlist tools: list_playlists, get_playlist_tracks, delete_playlist."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from ..client import LexiconClient
from ..errors import LexiconAPIError
from ..guardrails import dedupe_track_ids
from .tracks import COMPACT_TRACK_FIELDS, select_fields

# Bound concurrent /v1/track fetches so a large playlist doesn't flood the API.
_FETCH_CONCURRENCY = 8


# Lexicon playlist `type` codes.
_KINDS = {"1": "folder", "2": "playlist", "3": "smartlist"}


def _flatten(nodes: list[dict[str, Any]], prefix: str = "") -> list[dict[str, Any]]:
    """Depth-first walk of the tree (Lexicon's own order) into path-labelled rows."""
    rows: list[dict[str, Any]] = []
    for node in nodes:
        path = f"{prefix} / {node['name']}" if prefix else node["name"]
        rows.append(
            {
                "id": node["id"],
                "name": node["name"],
                "path": path,
                "kind": _KINDS.get(node.get("type"), node.get("type")),
                "parent_id": node.get("parentId"),
            }
        )
        rows.extend(_flatten(node.get("playlists") or [], path))
    return rows


async def list_playlists(client: LexiconClient, *, tree: bool = False) -> list[dict[str, Any]]:
    """Return every playlist, folder and smartlist.

    By default a flat list in Lexicon's own (depth-first) order, one row per node:
    `id`, `name`, `path` (folders joined with " / "), `kind`
    (folder / playlist / smartlist) and `parent_id`. The ROOT node, dates and
    null-valued fields are omitted, so a 200-node library is a few KB that can be
    scanned by name. `tree=True` returns `GET /v1/playlists` faithfully: a list
    whose first element is ROOT with nested `playlists`.

    Track membership is NOT included either way (the API does not provide counts
    in the tree) — use `get_playlist_tracks` for a playlist's contents.
    """
    data = await client.request("GET", "/v1/playlists")
    if tree:
        return data["playlists"]
    roots = data["playlists"]
    # Skip the synthetic ROOT container(s); start from their children.
    children = [c for r in roots for c in (r.get("playlists") or [])]
    return _flatten(children)


async def get_playlist_tracks(
    client: LexiconClient,
    playlist_id: int,
    *,
    fields: Sequence[str] | None = None,
    full: bool = False,
) -> list[dict[str, Any]]:
    """Return the track records for a playlist, in playlist order.

    `GET /v1/playlist?id=` gives ordered `trackIds` only, so this resolves each to
    a record via `GET /v1/track?id=` (there is no field filter on that endpoint,
    so trimming happens here). By default each record carries only
    COMPACT_TRACK_FIELDS — full records are ~3 KB apiece and a 100-track pull was
    375 KB. `fields` selects exactly the given fields; `full=True` returns the
    complete records (cue points, tempo markers, source blobs and all).

    Two real-world defenses apply:

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

    if full:
        return tracks
    keep = COMPACT_TRACK_FIELDS if fields is None else fields
    return [select_fields(t, keep) for t in tracks]


async def delete_playlist(
    client: LexiconClient, playlist_id: int, *, allow_playlist: bool = False
) -> dict[str, Any]:
    """Delete one smartlist (or, explicitly, one playlist); return what was removed.

    Reads the tree first so the decision is made on the node's real kind:

    - **folders are never deleted** — a folder delete cascades through every
      playlist under it, and a crate structure can be decades of curation;
    - **smartlists delete freely** — they are rule-defined and recreatable;
    - **playlists need ``allow_playlist=True``** — ordinary playlists are
      hand-built and there is no undo.

    Uses ``DELETE /v1/playlists`` with a JSON body ``{"ids": [...]}``; the
    documented query-string form fails (docs/upstream-api-issues.md).
    """
    rows = await list_playlists(client)
    node = next((r for r in rows if r["id"] == playlist_id), None)
    if node is None:
        raise ValueError(f"No playlist with id {playlist_id}. Use list_playlists to find it.")
    if node["kind"] == "folder":
        raise ValueError(
            f"Refusing to delete folder {node['path']!r} (id {playlist_id}): a folder "
            "delete removes everything under it. Delete its contents individually."
        )
    if node["kind"] == "playlist" and not allow_playlist:
        raise ValueError(
            f"{node['path']!r} (id {playlist_id}) is a playlist, not a smartlist. Pass "
            "allow_playlist=True to delete it; there is no undo."
        )
    await client.request("DELETE", "/v1/playlists", json={"ids": [playlist_id]})
    return {"id": playlist_id, "name": node["name"], "kind": node["kind"]}

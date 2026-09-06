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


_PLAYLIST_TYPE = "2"  # 1=folder, 2=playlist, 3=smartlist
# Same ceiling the tag tools use: a runaway id list is a curation accident.
_MAX_TRACKS_PER_CALL = 500


async def _fetch_playlist(client: LexiconClient, playlist_id: int) -> dict[str, Any]:
    """One playlist with its ordered trackIds. GET /v1/playlist is the only read
    that carries membership; /v1/playlists deliberately omits it."""
    data = await client.request("GET", "/v1/playlist", params={"id": playlist_id})
    return data["playlist"]


async def create_playlist(
    client: LexiconClient,
    name: str,
    *,
    parent_id: int | None = None,
    track_ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Create an ordinary playlist and return the new node.

    ``POST /v1/playlist`` creates it empty whatever you send: the body takes only
    name, type and parentId, and there is no way to seed membership. So when
    ``track_ids`` is given this adds them in a second call, which is exactly what
    :func:`add_tracks_to_playlist` does.

    Use ``parent_id`` to file it inside an existing folder; without one it lands
    at the bottom of the tree.
    """
    if not name.strip():
        raise ValueError("A playlist needs a name.")
    body: dict[str, Any] = {"name": name, "type": _PLAYLIST_TYPE}
    if parent_id is not None:
        body["parentId"] = parent_id

    created = await client.request("POST", "/v1/playlist", json=body)
    new_id = created["id"]
    if track_ids:
        await add_tracks_to_playlist(client, new_id, track_ids)

    node = await _fetch_playlist(client, new_id)
    return {
        "id": new_id,
        "name": node.get("name", name),
        "kind": "playlist",
        "parent_id": parent_id,
        "track_count": len(node.get("trackIds") or []),
    }


async def add_tracks_to_playlist(
    client: LexiconClient, playlist_id: int, track_ids: Sequence[int]
) -> dict[str, Any]:
    """Append tracks to a playlist, skipping any already in it.

    Lexicon's ``PATCH /v1/playlist-tracks`` appends whatever you send without
    checking, so sending an id twice puts the track in the crate twice. This
    reads the current membership first and sends only what is genuinely new,
    which makes the call safe to retry. ``skipped`` counts everything the caller
    sent that did not land, whether it was a duplicate in the request or already
    in the crate.

    Refuses folders and smartlists: a folder has no membership of its own, and a
    smartlist's is computed from its rules, so a manual append is either a
    no-op or a corruption. Caps a single call at 500 ids.
    """
    node = await _fetch_playlist(client, playlist_id)
    kind = {1: "folder", 2: "playlist", 3: "smartlist"}.get(int(node.get("type", 2)), "playlist")
    if kind != "playlist":
        raise ValueError(
            f"{node.get('name')!r} (id {playlist_id}) is a {kind}, not a playlist. "
            "A folder holds no tracks of its own and a smartlist computes its own "
            "membership from rules."
        )

    wanted = list(dict.fromkeys(int(t) for t in track_ids))  # dedupe, keep order
    if not wanted:
        raise ValueError("No track ids given.")
    if len(wanted) > _MAX_TRACKS_PER_CALL:
        raise ValueError(
            f"{len(wanted)} track ids in one call exceeds the {_MAX_TRACKS_PER_CALL} "
            "ceiling. Split it into batches so a mistake stays small."
        )

    present = set(node.get("trackIds") or [])
    new = [t for t in wanted if t not in present]
    if new:
        await client.request(
            "PATCH", "/v1/playlist-tracks", json={"id": playlist_id, "trackIds": new}
        )
    return {
        "id": playlist_id,
        "name": node.get("name"),
        "added": len(new),
        # counted against what the caller sent, so a repeated id and an
        # already-present one both read as "skipped"
        "skipped": len(track_ids) - len(new),
        "total": len(present) + len(new),
    }

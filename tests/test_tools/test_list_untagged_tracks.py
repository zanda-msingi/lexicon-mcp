"""Tests for list_untagged_tracks."""

import json

import httpx

from lexicon_mcp.tools.library import list_untagged_tracks
from lexicon_mcp.tools.tracks import COMPACT_TRACK_FIELDS

FULL = {
    "title": "T",
    "artist": "A",
    "bpm": 120,
    "key": "1D",
    "location": "/Volumes/ExampleDrive/T.mp3",
    "cuepoints": [{"id": 1}],
    "data": {"traktor": {}},
}


def _track(tid: int, tags: list[int]) -> dict:
    return {**FULL, "id": tid, "tags": tags}


async def test_playlist_scope_returns_compact_untagged_tracks_in_order(make_client):
    tracks = {101: [], 102: [1], 103: []}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/playlist":
            pl = {"id": 4, "name": "P", "type": "2", "trackIds": [101, 102, 103]}
            return httpx.Response(200, json={"data": {"playlist": pl}})
        tid = int(request.url.params["id"])
        return httpx.Response(200, json={"data": {"track": _track(tid, tracks[tid])}})

    async with make_client(handler) as client:
        result = await list_untagged_tracks(client, playlist_id=4)

    assert result["playlist_id"] == 4
    assert result["total_untagged"] == 2
    assert [t["id"] for t in result["tracks"]] == [101, 103]
    assert set(result["tracks"][0]) <= set(COMPACT_TRACK_FIELDS)
    assert "cuepoints" not in result["tracks"][0]


async def test_library_scope_scans_ids_and_tags_then_fetches_only_the_page(make_client):
    library = {1: [], 2: [7], 3: [], 4: [], 5: []}  # untagged: 1, 3, 4, 5
    scan_bodies: list[dict] = []
    fetched: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/tracks":
            body = json.loads(request.content)
            scan_bodies.append(body)
            rows = [{"id": i, "tags": t} for i, t in library.items()]
            page = rows[body["offset"] : body["offset"] + body["limit"]]
            return httpx.Response(200, json={"data": {"total": len(rows), "tracks": page}})
        if request.url.path == "/v1/track":
            tid = int(request.url.params["id"])
            fetched.append(tid)
            return httpx.Response(200, json={"data": {"track": _track(tid, library[tid])}})
        raise AssertionError(request.url.path)

    async with make_client(handler) as client:
        result = await list_untagged_tracks(client, limit=2, offset=1)

    assert all(b["fields"] == ["id", "tags"] for b in scan_bodies)
    assert result["total_untagged"] == 4
    assert result["offset"] == 1
    assert result["returned"] == 2
    assert [t["id"] for t in result["tracks"]] == [3, 4]
    assert sorted(fetched) == [3, 4]  # only the page, never the whole library
    assert "playlist_id" not in result


async def test_library_scope_with_nothing_untagged(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        rows = [{"id": 1, "tags": [1]}]
        return httpx.Response(200, json={"data": {"total": 1, "tracks": rows}})

    async with make_client(handler) as client:
        result = await list_untagged_tracks(client)

    assert result == {"total_untagged": 0, "offset": 0, "returned": 0, "tracks": []}

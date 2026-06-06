"""Tests for get_playlist_tracks."""

import httpx

from lexicon_mcp.tools.playlists import get_playlist_tracks


async def test_dedupes_trackids_and_fetches_full_tracks_in_order(make_client, load_fixture):
    playlist = load_fixture("playlist.json")  # trackIds [101,102,103,102,101]
    track_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/playlist":
            return httpx.Response(200, json={"data": {"playlist": playlist}})
        if request.url.path == "/v1/track":
            tid = int(request.url.params["id"])
            track_calls.append(tid)
            return httpx.Response(200, json={"data": {"track": {"id": tid, "title": f"T{tid}"}}})
        raise AssertionError(f"unexpected path {request.url.path}")

    async with make_client(handler) as client:
        result = await get_playlist_tracks(client, 4)

    # Deduped to 3 unique ids, fetched once each, returned in playlist order.
    assert [t["id"] for t in result] == [101, 102, 103]
    assert sorted(track_calls) == [101, 102, 103]
    assert len(track_calls) == 3


async def test_skips_tracks_that_no_longer_exist(make_client):
    playlist = {"id": 4, "name": "P", "type": "2", "trackIds": [101, 102, 103]}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/playlist":
            return httpx.Response(200, json={"data": {"playlist": playlist}})
        tid = int(request.url.params["id"])
        if tid == 102:  # since-deleted track
            return httpx.Response(400, json={"message": "not found", "errorCode": 4})
        return httpx.Response(200, json={"data": {"track": {"id": tid}}})

    async with make_client(handler) as client:
        result = await get_playlist_tracks(client, 4)

    assert [t["id"] for t in result] == [101, 103]


async def test_empty_playlist_returns_empty_list(make_client):
    playlist = {"id": 9, "name": "Empty", "type": "2", "trackIds": []}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"playlist": playlist}})

    async with make_client(handler) as client:
        result = await get_playlist_tracks(client, 9)

    assert result == []

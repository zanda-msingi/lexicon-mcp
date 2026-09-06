"""Tests for create_playlist and add_tracks_to_playlist."""

import json

import httpx
import pytest

from lexicon_mcp.tools.playlists import add_tracks_to_playlist, create_playlist


def _recorder(calls, *, new_id=216, existing=None):
    """A stateful stand-in for Lexicon.

    Stateful on purpose: an append actually lands in `existing`, so a tool that
    creates a playlist and then seeds it reads back an empty crate first, the way
    the real API behaves. A fake that returned the final state would hide that.
    """
    existing = existing if existing is not None else {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read() or b"{}")
        calls.append((request.method, request.url.path, payload))
        if request.url.path == "/v1/playlist" and request.method == "POST":
            existing[new_id] = {
                "id": new_id,
                "name": payload["name"],
                "type": int(payload["type"]),
                "trackIds": [],
            }
            return httpx.Response(200, json={"data": {"id": new_id}})
        if request.url.path == "/v1/playlist" and request.method == "GET":
            return httpx.Response(
                200, json={"data": {"playlist": existing[int(request.url.params["id"])]}}
            )
        if request.url.path == "/v1/playlist-tracks":
            existing[payload["id"]]["trackIds"] += payload["trackIds"]
            return httpx.Response(200, json={"data": {}})
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    return handler


async def test_create_playlist_posts_type_2_and_returns_the_new_node(make_client):
    calls: list = []
    async with make_client(_recorder(calls)) as client:
        node = await create_playlist(client, "zz-new")

    assert ("POST", "/v1/playlist", {"name": "zz-new", "type": "2"}) in calls
    assert node["id"] == 216 and node["kind"] == "playlist"


async def test_create_playlist_passes_parent_and_seeds_tracks(make_client):
    calls: list = []
    async with make_client(_recorder(calls)) as client:
        node = await create_playlist(client, "zz-new", parent_id=62, track_ids=[7, 8])

    post = next(c for c in calls if c[:2] == ("POST", "/v1/playlist"))
    assert post[2]["parentId"] == 62
    add = next(c for c in calls if c[1] == "/v1/playlist-tracks")
    assert add[0] == "PATCH" and add[2] == {"id": 216, "trackIds": [7, 8]}
    assert node["track_count"] == 2


async def test_add_tracks_dedupes_against_what_is_already_there(make_client):
    calls: list = []
    existing = {9: {"id": 9, "name": "crate", "type": 2, "trackIds": [1, 2, 3]}}

    async with make_client(_recorder(calls, existing=existing)) as client:
        res = await add_tracks_to_playlist(client, 9, [3, 4, 4, 5])

    add = next(c for c in calls if c[1] == "/v1/playlist-tracks")
    assert add[2]["trackIds"] == [4, 5], "already-present and duplicate ids must be dropped"
    assert res == {"id": 9, "name": "crate", "added": 2, "skipped": 2, "total": 5}


async def test_add_tracks_is_a_no_op_when_everything_is_already_there(make_client):
    calls: list = []
    existing = {9: {"id": 9, "name": "crate", "type": 2, "trackIds": [1, 2]}}

    async with make_client(_recorder(calls, existing=existing)) as client:
        res = await add_tracks_to_playlist(client, 9, [1, 2])

    assert not [c for c in calls if c[1] == "/v1/playlist-tracks"]
    assert res["added"] == 0 and res["total"] == 2


async def test_add_tracks_refuses_a_folder_or_smartlist(make_client):
    existing = {9: {"id": 9, "name": "2023", "type": 1, "trackIds": []}}

    async with make_client(_recorder([], existing=existing)) as client:
        with pytest.raises(ValueError, match="folder"):
            await add_tracks_to_playlist(client, 9, [1])


async def test_add_tracks_rejects_an_empty_id_list(make_client):
    existing = {9: {"id": 9, "name": "crate", "type": 2, "trackIds": []}}

    async with make_client(_recorder([], existing=existing)) as client:
        with pytest.raises(ValueError, match="No track ids"):
            await add_tracks_to_playlist(client, 9, [])


async def test_add_tracks_enforces_the_bulk_ceiling(make_client):
    existing = {9: {"id": 9, "name": "crate", "type": 2, "trackIds": []}}

    async with make_client(_recorder([], existing=existing)) as client:
        with pytest.raises(ValueError, match="500"):
            await add_tracks_to_playlist(client, 9, list(range(1, 502)))

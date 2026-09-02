"""Tests for delete_playlist."""

import json

import httpx
import pytest

from lexicon_mcp.tools.playlists import delete_playlist


def _handler(tree, deletes: list):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/playlists" and request.method == "GET":
            return httpx.Response(200, json={"data": tree})
        if request.url.path == "/v1/playlists" and request.method == "DELETE":
            deletes.append(json.loads(request.content))
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    return handler


async def test_deletes_a_smartlist_by_json_body_and_reports_it(make_client, load_fixture):
    deletes: list = []
    async with make_client(_handler(load_fixture("playlists.json"), deletes)) as client:
        result = await delete_playlist(client, 7)

    assert deletes == [{"ids": [7]}]
    assert result == {"id": 7, "name": "Example Smartlist", "kind": "smartlist"}


async def test_refuses_folders_outright(make_client, load_fixture):
    deletes: list = []
    async with make_client(_handler(load_fixture("playlists.json"), deletes)) as client:
        with pytest.raises(ValueError, match="folder"):
            await delete_playlist(client, 3, allow_playlist=True)

    assert deletes == []


async def test_refuses_a_playlist_unless_allowed(make_client, load_fixture):
    deletes: list = []
    async with make_client(_handler(load_fixture("playlists.json"), deletes)) as client:
        with pytest.raises(ValueError, match="allow_playlist"):
            await delete_playlist(client, 4)

    assert deletes == []


async def test_deletes_a_playlist_when_allowed(make_client, load_fixture):
    deletes: list = []
    async with make_client(_handler(load_fixture("playlists.json"), deletes)) as client:
        result = await delete_playlist(client, 4, allow_playlist=True)

    assert deletes == [{"ids": [4]}]
    assert result == {"id": 4, "name": "Example Playlist A", "kind": "playlist"}


async def test_unknown_id_is_an_error_before_any_delete(make_client, load_fixture):
    deletes: list = []
    async with make_client(_handler(load_fixture("playlists.json"), deletes)) as client:
        with pytest.raises(ValueError, match="999"):
            await delete_playlist(client, 999)

    assert deletes == []

"""Tests for search_tracks."""

import json

import httpx
import pytest

from lexicon_mcp.guardrails import UnsafeFilterError
from lexicon_mcp.tools.tracks import search_tracks


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


async def test_sends_filter_in_body_and_returns_total_and_tracks(make_client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = _body(request)
        return httpx.Response(200, json={"data": {"total": 2, "tracks": [{"id": 1}, {"id": 2}]}})

    async with make_client(handler) as client:
        result = await search_tracks(client, {"artist": "Daft Punk"})

    assert seen["path"] == "/v1/search/tracks"
    assert seen["body"]["filter"] == {"artist": "Daft Punk"}
    assert result["total"] == 2
    assert [t["id"] for t in result["tracks"]] == [1, 2]


async def test_rejects_unsafe_filter_before_any_request(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not hit the API with an unsafe filter")

    async with make_client(handler) as client:
        with pytest.raises(UnsafeFilterError):
            await search_tracks(client, {"id": 5})  # silent-return-all field


async def test_normalizes_sort_to_always_include_dir(make_client):
    # A sort object without `dir` crashes the Lexicon server; we must add it.
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = _body(request)
        return httpx.Response(200, json={"data": {"total": 0, "tracks": []}})

    async with make_client(handler) as client:
        await search_tracks(client, {"artist": "X"}, sort=["bpm", {"field": "key"}])

    assert seen["body"]["sort"] == [
        {"field": "bpm", "dir": "asc"},
        {"field": "key", "dir": "asc"},
    ]


async def test_caps_returned_tracks_but_reports_true_total(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        tracks = [{"id": i} for i in range(5)]
        return httpx.Response(200, json={"data": {"total": 5, "tracks": tracks}})

    async with make_client(handler) as client:
        result = await search_tracks(client, {"artist": "X"}, limit=2)

    assert result["total"] == 5  # the real match count, not truncated
    assert result["returned"] == 2
    assert len(result["tracks"]) == 2


async def test_fields_strips_the_columns_lexicon_forces_in(make_client):
    # Lexicon always adds type/archived/location even when `fields` excludes them.
    def handler(request: httpx.Request) -> httpx.Response:
        track = {"id": 1, "title": "T", "type": "0", "archived": 0, "location": "/x.mp3"}
        return httpx.Response(200, json={"data": {"total": 1, "tracks": [track]}})

    async with make_client(handler) as client:
        result = await search_tracks(client, {"artist": "X"}, fields=["id", "title"])

    assert result["tracks"] == [{"id": 1, "title": "T"}]


async def test_without_fields_search_returns_records_untouched(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        track = {"id": 1, "title": "T", "type": "0", "location": "/x.mp3"}
        return httpx.Response(200, json={"data": {"total": 1, "tracks": [track]}})

    async with make_client(handler) as client:
        result = await search_tracks(client, {"artist": "X"})

    assert result["tracks"] == [{"id": 1, "title": "T", "type": "0", "location": "/x.mp3"}]

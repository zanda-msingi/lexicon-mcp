"""Tests for get_track."""

import httpx
import pytest

from lexicon_mcp.errors import LexiconAPIError
from lexicon_mcp.tools.tracks import get_track


async def test_returns_full_track_record(make_client, load_fixture):
    track = load_fixture("track.json")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["id"] = request.url.params.get("id")
        return httpx.Response(200, json={"data": {"track": track}})

    async with make_client(handler) as client:
        result = await get_track(client, 1)

    assert seen["path"] == "/v1/track"
    assert seen["id"] == "1"
    assert result["id"] == 1
    assert result["title"] == "Example Track"


async def test_missing_track_raises_api_error(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "not found", "errorCode": 4})

    async with make_client(handler) as client:
        with pytest.raises(LexiconAPIError):
            await get_track(client, 999999)

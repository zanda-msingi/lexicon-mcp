"""Tests for the thin async Lexicon HTTP client.

We exercise the client through httpx's MockTransport, so these run the real
request/response/envelope code path with no network.
"""

import httpx
import pytest

from lexicon_mcp.client import LexiconClient
from lexicon_mcp.errors import LexiconAPIError, LexiconConnectionError


def _client(handler, base_url="http://localhost:48624"):
    return LexiconClient(base_url=base_url, transport=httpx.MockTransport(handler))


async def test_request_unwraps_data_envelope():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"playlists": [{"id": 1}]}})

    async with _client(handler) as client:
        data = await client.request("GET", "/v1/playlists")
    assert data == {"playlists": [{"id": 1}]}


async def test_error_envelope_raises_lexicon_api_error_with_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "API / does not exist", "errorCode": 4})

    async with _client(handler) as client:
        with pytest.raises(LexiconAPIError) as exc:
            await client.request("GET", "/v1/nope")
    assert exc.value.error_code == 4
    assert "does not exist" in str(exc.value)


async def test_connection_refused_raises_actionable_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    async with _client(handler) as client:
        with pytest.raises(LexiconConnectionError) as exc:
            await client.request("GET", "/v1/playlists")
    msg = str(exc.value)
    # Actionable: names the address and points at the cause.
    assert "localhost:48624" in msg
    assert "Lexicon" in msg


async def test_default_base_url_is_localhost_48624():
    assert LexiconClient().base_url == "http://localhost:48624"


async def test_get_can_send_a_json_body():
    # The sort param only works in a JSON body on GET (upstream quirk), so the
    # client must support a body on GET requests.
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["content"] = request.content
        return httpx.Response(200, json={"data": {"tracks": []}})

    async with _client(handler) as client:
        await client.request(
            "GET", "/v1/search/tracks", json={"sort": [{"field": "bpm", "dir": "asc"}]}
        )
    assert b"sort" in seen["content"]
    assert b'"dir"' in seen["content"]

"""Tests for set_custom_tags (REPLACE semantics)."""

import json

import httpx

from lexicon_mcp.tools.tags import set_custom_tags


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


async def test_replaces_tags_via_patch_then_refetches(make_client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH" and request.url.path == "/v1/track":
            seen["patch_body"] = _body(request)
            return httpx.Response(200, json={})  # tag edits return empty {}
        if request.method == "GET" and request.url.path == "/v1/track":
            seen["refetch_id"] = request.url.params.get("id")
            return httpx.Response(200, json={"data": {"track": {"id": 42, "tags": [1, 2, 3]}}})
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    async with make_client(handler) as client:
        result = await set_custom_tags(client, 42, [1, 2, 3])

    # Exact replace payload, wrapped in edits.
    assert seen["patch_body"] == {"id": 42, "edits": {"tags": [1, 2, 3]}}
    # Re-fetched (PATCH response is unreliable), returns the confirmed track.
    assert seen["refetch_id"] == "42"
    assert result["tags"] == [1, 2, 3]


async def test_empty_list_clears_tags(make_client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH":
            seen["patch_body"] = _body(request)
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"data": {"track": {"id": 42, "tags": []}}})

    async with make_client(handler) as client:
        result = await set_custom_tags(client, 42, [])

    assert seen["patch_body"] == {"id": 42, "edits": {"tags": []}}
    assert result["tags"] == []

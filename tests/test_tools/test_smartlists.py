"""Tests for create_smartlist."""

import json

import httpx

from lexicon_mcp.tools.smartlists import create_smartlist


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


async def test_creates_type3_smartlist_with_rules_then_refetches(make_client):
    seen = {}
    rules = [{"field": "bpm", "operator": "NumberGreaterThan", "values": [120]}]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/playlist":
            seen["post_body"] = _body(request)
            return httpx.Response(200, json={"data": {"id": 300}})
        if request.method == "GET" and request.url.path == "/v1/playlist":
            seen["refetch_id"] = request.url.params.get("id")
            return httpx.Response(
                200,
                json={
                    "data": {
                        "playlist": {
                            "id": 300,
                            "name": "Fast tracks",
                            "type": "3",
                            "smartlist": {"matchAll": True, "rules": rules},
                        }
                    }
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    async with make_client(handler) as client:
        result = await create_smartlist(client, "Fast tracks", rules)

    assert seen["post_body"] == {
        "name": "Fast tracks",
        "type": "3",
        "smartlist": {"matchAll": True, "rules": rules},
    }
    assert seen["refetch_id"] == "300"
    assert result["id"] == 300
    assert result["type"] == "3"
    assert result["smartlist"]["rules"] == rules


async def test_match_all_false_and_parent_id_are_passed_through(make_client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            seen["post_body"] = _body(request)
            return httpx.Response(200, json={"data": {"id": 7}})
        return httpx.Response(200, json={"data": {"playlist": {"id": 7}}})

    async with make_client(handler) as client:
        await create_smartlist(client, "Any", [], match_all=False, parent_id=2)

    assert seen["post_body"]["smartlist"]["matchAll"] is False
    assert seen["post_body"]["parentId"] == 2

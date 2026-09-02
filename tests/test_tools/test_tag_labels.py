"""Tests for label resolution in the tag tools (v0.2)."""

import json

import httpx
import pytest

from lexicon_mcp.tools.tags import bulk_apply_tags, resolve_tag_ids, set_custom_tags

TAXONOMY = {
    "categories": [
        {"id": 1, "label": "Genre", "tags": [1, 2]},
        {"id": 2, "label": "Undertow", "tags": [3]},
        {"id": 3, "label": "Mood", "tags": [9]},
    ],
    "tags": [
        {"id": 1, "categoryId": 1, "label": "Afro House"},
        {"id": 2, "categoryId": 1, "label": "House"},
        {"id": 3, "categoryId": 2, "label": "deep"},
        {"id": 9, "categoryId": 3, "label": "Deep"},
    ],
}


def _taxonomy_handler(calls: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url.path)
        assert request.url.path == "/v1/tags"
        return httpx.Response(200, json={"data": TAXONOMY})

    return handler


async def test_ints_pass_through_without_reading_the_taxonomy(make_client):
    calls: list = []
    async with make_client(_taxonomy_handler(calls)) as client:
        assert await resolve_tag_ids(client, [1, 55]) == [1, 55]
    assert calls == []


async def test_category_slash_label_resolves_within_that_category(make_client):
    async with make_client(_taxonomy_handler()) as client:
        assert await resolve_tag_ids(client, ["Undertow/deep", "Mood/Deep"]) == [3, 9]


async def test_bare_label_resolves_by_exact_match(make_client):
    async with make_client(_taxonomy_handler()) as client:
        assert await resolve_tag_ids(client, ["Afro House", 2, "deep"]) == [1, 2, 3]


async def test_bare_label_falls_back_to_unique_case_insensitive_match(make_client):
    async with make_client(_taxonomy_handler()) as client:
        assert await resolve_tag_ids(client, ["afro house"]) == [1]


async def test_ambiguous_case_insensitive_label_lists_the_candidates(make_client):
    async with make_client(_taxonomy_handler()) as client:
        with pytest.raises(ValueError, match="Undertow/deep.*Mood/Deep|Mood/Deep.*Undertow/deep"):
            await resolve_tag_ids(client, ["DEEP"])


async def test_unknown_label_names_it(make_client):
    async with make_client(_taxonomy_handler()) as client:
        with pytest.raises(ValueError, match="Amapiano"):
            await resolve_tag_ids(client, ["Amapiano"])


async def test_unknown_category_in_slash_form_names_it(make_client):
    async with make_client(_taxonomy_handler()) as client:
        with pytest.raises(ValueError, match="Origin"):
            await resolve_tag_ids(client, ["Origin/Shona"])


async def test_taxonomy_is_read_once_per_call(make_client):
    calls: list = []
    async with make_client(_taxonomy_handler(calls)) as client:
        await resolve_tag_ids(client, ["House", "deep", "Genre/Afro House"])
    assert calls == ["/v1/tags"]


async def test_set_custom_tags_accepts_labels(make_client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/tags":
            return httpx.Response(200, json={"data": TAXONOMY})
        if request.method == "PATCH":
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"data": {"track": {"id": 841, "tags": [1, 3]}}})

    async with make_client(handler) as client:
        track = await set_custom_tags(client, 841, ["Afro House", "Undertow/deep"])

    assert seen["body"] == {"id": 841, "edits": {"tags": [1, 3]}}
    assert track["tags"] == [1, 3]


async def test_bulk_apply_tags_accepts_labels(make_client):
    patched = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/tags":
            return httpx.Response(200, json={"data": TAXONOMY})
        if request.method == "PATCH":
            body = json.loads(request.content)
            patched[body["id"]] = body["edits"]["tags"]
            return httpx.Response(200, json={})
        tid = int(request.url.params["id"])
        return httpx.Response(200, json={"data": {"track": {"id": tid, "tags": [2]}}})

    async with make_client(handler) as client:
        summary = await bulk_apply_tags(client, [10, 11], ["Afro House"], expected_count=2)

    assert summary["updated"] == 2
    assert patched == {10: [2, 1], 11: [2, 1]}

"""Tests for bulk_apply_tags (ADD/merge semantics + safety guardrail)."""

import json

import httpx
import pytest

from lexicon_mcp.guardrails import BulkWriteSafetyError
from lexicon_mcp.tools.tags import bulk_apply_tags


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


def _make_handler(tags_by_id: dict, patches: list):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/track":
            tid = int(request.url.params["id"])
            return httpx.Response(
                200, json={"data": {"track": {"id": tid, "tags": tags_by_id[tid]}}}
            )
        if request.method == "PATCH" and request.url.path == "/v1/track":
            patches.append(_body(request))
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    return handler


async def test_merges_tags_into_each_track_without_wiping(make_client):
    patches = []
    handler = _make_handler({101: [1], 102: []}, patches)

    async with make_client(handler) as client:
        result = await bulk_apply_tags(client, [101, 102], [5])

    patched = {p["id"]: p["edits"]["tags"] for p in patches}
    assert patched[101] == [1, 5]  # existing tag preserved, new added
    assert patched[102] == [5]
    assert result["updated"] == 2


async def test_skips_track_that_already_has_all_tags(make_client):
    patches = []
    handler = _make_handler({101: [5, 9]}, patches)

    async with make_client(handler) as client:
        result = await bulk_apply_tags(client, [101], [5])

    assert patches == []  # nothing to change -> no write
    assert result["unchanged"] == 1
    assert result["updated"] == 0


async def test_rejects_when_over_ceiling_before_any_write(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not touch the API when over the ceiling")

    async with make_client(handler) as client:
        with pytest.raises(BulkWriteSafetyError):
            await bulk_apply_tags(client, [1, 2, 3], [5], ceiling=2)


async def test_rejects_on_expected_count_mismatch_before_any_write(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not write when the count check fails")

    async with make_client(handler) as client:
        with pytest.raises(BulkWriteSafetyError):
            await bulk_apply_tags(client, [1, 2], [5], expected_count=3)


async def test_rejects_empty_track_set(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not write to an empty set")

    async with make_client(handler) as client:
        with pytest.raises(BulkWriteSafetyError):
            await bulk_apply_tags(client, [], [5])


async def test_dedupes_input_track_ids(make_client):
    patches = []
    handler = _make_handler({101: [], 102: []}, patches)

    async with make_client(handler) as client:
        # 101 appears twice; must be treated once, and the count check sees 2.
        result = await bulk_apply_tags(client, [101, 101, 102], [5], expected_count=2)

    assert result["requested"] == 2
    assert sorted(p["id"] for p in patches) == [101, 102]

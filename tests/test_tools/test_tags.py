"""Tests for tag tools."""

import httpx

from lexicon_mcp.tools.tags import list_custom_tag_categories


async def test_groups_full_tag_objects_under_their_categories(make_client, load_fixture):
    tags_payload = load_fixture("tags.json")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"data": tags_payload})

    async with make_client(handler) as client:
        result = await list_custom_tag_categories(client)

    assert seen["path"] == "/v1/tags"
    by_label = {c["label"]: c for c in result}
    assert [t["label"] for t in by_label["Genre"]["tags"]] == ["House", "Disco"]
    assert [t["label"] for t in by_label["Mood"]["tags"]] == ["Energetic"]
    assert by_label["Mix"]["tags"] == []  # category with no tags


async def test_membership_uses_categoryId_not_the_stale_category_tags_list(make_client):
    # Upstream quirk: category.tags can be out of sync; tag.categoryId is truth.
    payload = {
        "categories": [{"id": 1, "label": "Genre", "tags": [999]}],  # stale/bogus
        "tags": [{"id": 7, "categoryId": 1, "label": "House", "shortcut": None}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": payload})

    async with make_client(handler) as client:
        result = await list_custom_tag_categories(client)

    assert [t["label"] for t in result[0]["tags"]] == ["House"]


async def test_empty_taxonomy_returns_empty_list(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"categories": [], "tags": []}})

    async with make_client(handler) as client:
        result = await list_custom_tag_categories(client)

    assert result == []

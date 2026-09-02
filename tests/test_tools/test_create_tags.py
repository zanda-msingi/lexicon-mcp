"""Tests for create_tag_category and create_tag."""

import json

import httpx
import pytest

from lexicon_mcp.errors import LexiconAPIError
from lexicon_mcp.tools.tags import create_tag, create_tag_category


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


async def test_create_tag_category_posts_label_and_color_and_returns_object(make_client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"], seen["path"], seen["body"] = (
            request.method,
            request.url.path,
            _body(request),
        )
        # Real shape: top-level object, no {"data": ...} wrapper.
        return httpx.Response(
            200, json={"id": 5, "label": "Undertow", "position": 4, "color": "#123456", "tags": []}
        )

    async with make_client(handler) as client:
        created = await create_tag_category(client, "Undertow", color="#123456")

    assert (seen["method"], seen["path"]) == ("POST", "/v1/tag-category")
    assert seen["body"] == {"label": "Undertow", "color": "#123456"}
    assert created["id"] == 5 and created["label"] == "Undertow"


async def test_create_tag_category_omits_color_when_not_given(make_client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = _body(request)
        return httpx.Response(200, json={"id": 6, "label": "Origin", "position": 5, "tags": []})

    async with make_client(handler) as client:
        await create_tag_category(client, "Origin")

    assert seen["body"] == {"label": "Origin"}


async def test_create_tag_posts_category_and_label_and_returns_object(make_client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"], seen["path"], seen["body"] = (
            request.method,
            request.url.path,
            _body(request),
        )
        return httpx.Response(200, json={"id": 77, "categoryId": 5, "label": "deep", "position": 0})

    async with make_client(handler) as client:
        created = await create_tag(client, 5, "deep")

    assert (seen["method"], seen["path"]) == ("POST", "/v1/tag")
    assert seen["body"] == {"categoryId": 5, "label": "deep"}
    assert created == {"id": 77, "categoryId": 5, "label": "deep", "position": 0}


async def test_duplicate_label_surfaces_lexicons_error(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"message": "Category label already exists", "errorCode": 107}
        )

    async with make_client(handler) as client:
        with pytest.raises(LexiconAPIError, match="already exists") as excinfo:
            await create_tag_category(client, "Genre")

    assert excinfo.value.error_code == 107

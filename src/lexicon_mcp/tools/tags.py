"""Custom tag tools: list_custom_tag_categories, set_custom_tags, bulk_apply_tags."""

from __future__ import annotations

from typing import Any

from ..client import LexiconClient


async def list_custom_tag_categories(client: LexiconClient) -> list[dict[str, Any]]:
    """Return the custom-tag taxonomy: each category with its full tag objects.

    Reads `GET /v1/tags` (which returns categories and tags as parallel lists) and
    nests them for convenience. Membership is computed from each tag's
    `categoryId` — NOT from `category.tags`, which the API can leave stale
    (docs/upstream-api-issues.md). Returns an empty list when no taxonomy exists.
    """
    data = await client.request("GET", "/v1/tags")
    categories = data.get("categories", [])
    tags = data.get("tags", [])

    by_category: dict[Any, list[dict[str, Any]]] = {}
    for tag in tags:
        by_category.setdefault(tag.get("categoryId"), []).append(tag)

    return [{**category, "tags": by_category.get(category["id"], [])} for category in categories]

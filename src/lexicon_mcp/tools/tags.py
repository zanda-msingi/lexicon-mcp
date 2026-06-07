"""Custom tag tools: list_custom_tag_categories, set_custom_tags, bulk_apply_tags."""

from __future__ import annotations

from typing import Any

from ..client import LexiconClient
from .tracks import get_track


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


async def set_custom_tags(
    client: LexiconClient, track_id: int, tag_ids: list[int]
) -> dict[str, Any]:
    """Set a track's custom tags to EXACTLY ``tag_ids`` (replace), return the track.

    REPLACE semantics, matching the tool's name and the raw API: the given list
    becomes the track's complete tag set. To *add* a tag without disturbing
    others, read the track first and set the union (the LLM composes this); to
    add across many tracks safely, use ``bulk_apply_tags``. Pass ``[]`` to clear.

    The PATCH response is unreliable for tag edits (often an empty ``{}``), so we
    re-fetch and return the confirmed track state.
    """
    await client.request(
        "PATCH", "/v1/track", json={"id": track_id, "edits": {"tags": list(tag_ids)}}
    )
    return await get_track(client, track_id)

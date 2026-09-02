"""Custom tag tools: list_custom_tag_categories, create_tag_category, create_tag,
set_custom_tags, bulk_apply_tags."""

from __future__ import annotations

import asyncio
from typing import Any

from ..client import LexiconClient
from ..errors import LexiconAPIError
from ..guardrails import (
    DEFAULT_BULK_WRITE_CEILING,
    assert_bulk_within_ceiling,
    dedupe_track_ids,
)
from .tracks import get_track

# Bound concurrent read+write pairs during a bulk operation.
_BULK_CONCURRENCY = 8


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


async def create_tag_category(
    client: LexiconClient, label: str, *, color: str | None = None
) -> dict[str, Any]:
    """Create a custom-tag category via `POST /v1/tag-category`; return it.

    The response is the new category object at the top level (no `data`
    wrapper — an upstream quirk the client already handles). Lexicon enforces
    unique category labels itself (errorCode 107), so a duplicate surfaces as a
    LexiconAPIError with Lexicon's own message rather than a silent no-op.
    """
    body: dict[str, Any] = {"label": label}
    if color is not None:
        body["color"] = color
    return await client.request("POST", "/v1/tag-category", json=body)


async def create_tag(client: LexiconClient, category_id: int, label: str) -> dict[str, Any]:
    """Create a custom tag in a category via `POST /v1/tag`; return it.

    Tag labels are unique across the WHOLE library (case-sensitive), enforced
    by Lexicon (errorCode 106); a duplicate surfaces as a LexiconAPIError.
    """
    return await client.request("POST", "/v1/tag", json={"categoryId": category_id, "label": label})


TagRef = int | str


async def resolve_tag_ids(client: LexiconClient, tag_refs: list[TagRef]) -> list[int]:
    """Turn tag references into tag ids against the LIVE taxonomy.

    A reference is an int (passed through untouched) or a string: either
    ``"Category/Label"`` or a bare ``"Label"``. Tag labels are unique across the
    library (Lexicon enforces it, case-sensitively), so a bare label resolves by
    exact match first and falls back to a case-insensitive match only when that
    is unique; an ambiguous fallback or an unknown label raises ValueError
    naming the options. The taxonomy is read at most once per call, and not at
    all when every reference is an int. Nothing about the taxonomy is baked in.
    """
    if all(isinstance(ref, int) for ref in tag_refs):
        return list(tag_refs)

    taxonomy = await client.request("GET", "/v1/tags")
    tags = taxonomy.get("tags", [])
    categories = {c["id"]: c.get("label", "") for c in taxonomy.get("categories", [])}

    def qualified(tag: dict[str, Any]) -> str:
        return f"{categories.get(tag.get('categoryId'), '?')}/{tag.get('label')} (id {tag['id']})"

    resolved: list[int] = []
    for ref in tag_refs:
        if isinstance(ref, int):
            resolved.append(ref)
            continue
        if "/" in ref:
            cat_label, _, label = ref.partition("/")
            cat_ids = [
                i for i, name in categories.items() if name.lower() == cat_label.strip().lower()
            ]
            if not cat_ids:
                raise ValueError(
                    f"Unknown tag category {cat_label.strip()!r} in {ref!r}. "
                    f"Categories: {sorted(categories.values())}"
                )
            pool = [t for t in tags if t.get("categoryId") in cat_ids]
            wanted = label.strip()
        else:
            pool = tags
            wanted = ref.strip()

        exact = [t for t in pool if t.get("label") == wanted]
        if len(exact) == 1:
            resolved.append(exact[0]["id"])
            continue
        loose = [t for t in pool if (t.get("label") or "").lower() == wanted.lower()]
        if len(loose) == 1:
            resolved.append(loose[0]["id"])
            continue
        if loose:
            raise ValueError(
                f"Tag label {ref!r} is ambiguous; use Category/Label. "
                f"Matches: {', '.join(qualified(t) for t in loose)}"
            )
        raise ValueError(
            f"Unknown tag {ref!r}. Use list_custom_tag_categories to see the taxonomy, "
            "or create_tag to add it."
        )
    return resolved


async def set_custom_tags(
    client: LexiconClient, track_id: int, tag_ids: list[TagRef]
) -> dict[str, Any]:
    """Set a track's custom tags to EXACTLY ``tag_ids`` (replace), return the track.

    REPLACE semantics, matching the tool's name and the raw API: the given list
    becomes the track's complete tag set. To *add* a tag without disturbing
    others, read the track first and set the union (the LLM composes this); to
    add across many tracks safely, use ``bulk_apply_tags``. Pass ``[]`` to clear.

    Entries may be tag ids or labels (``"Genre/Afro House"`` or ``"Afro House"``);
    labels are resolved against the live taxonomy before any write.

    The PATCH response is unreliable for tag edits (often an empty ``{}``), so we
    re-fetch and return the confirmed track state.
    """
    ids = await resolve_tag_ids(client, tag_ids)
    await client.request("PATCH", "/v1/track", json={"id": track_id, "edits": {"tags": ids}})
    return await get_track(client, track_id)


async def bulk_apply_tags(
    client: LexiconClient,
    track_ids: list[int],
    tag_ids: list[TagRef],
    *,
    expected_count: int | None = None,
    ceiling: int = DEFAULT_BULK_WRITE_CEILING,
) -> dict[str, Any]:
    """Add ``tag_ids`` to each of ``track_ids`` (merge, never wipe). Returns a summary.

    ADD semantics: for each track we read its current tags and write back the
    union, so existing tags are preserved — the safe meaning of "apply to many".
    ``tag_ids`` entries may be ids or labels (resolved once, before any write).

    Safety: input track ids are deduped, then the count-before-bulk-write guard
    runs BEFORE any write. It refuses an empty set, a set larger than ``ceiling``
    (the classic symptom of a search silently returning the whole library), or a
    mismatch with ``expected_count`` if the caller asserts one. A track that
    errors individually is reported as failed without aborting the batch; a
    connection error aborts.
    """
    track_ids = dedupe_track_ids(track_ids)
    assert_bulk_within_ceiling(track_ids, ceiling=ceiling, expected_count=expected_count)

    new_tags = await resolve_tag_ids(client, tag_ids)
    sem = asyncio.Semaphore(_BULK_CONCURRENCY)

    async def apply(track_id: int) -> dict[str, Any]:
        async with sem:
            track = await get_track(client, track_id)
            current = track.get("tags") or []
            merged = list(dict.fromkeys([*current, *new_tags]))
            if merged == current:
                return {"track_id": track_id, "status": "unchanged", "tags": current}
            await client.request(
                "PATCH", "/v1/track", json={"id": track_id, "edits": {"tags": merged}}
            )
            return {"track_id": track_id, "status": "updated", "tags": merged}

    outcomes = await asyncio.gather(*(apply(tid) for tid in track_ids), return_exceptions=True)

    results: list[dict[str, Any]] = []
    for track_id, outcome in zip(track_ids, outcomes, strict=True):
        if isinstance(outcome, LexiconAPIError):
            results.append({"track_id": track_id, "status": "failed", "error": str(outcome)})
        elif isinstance(outcome, BaseException):
            raise outcome  # connection/unknown error -> abort the whole batch
        else:
            results.append(outcome)

    updated = sum(1 for r in results if r["status"] == "updated")
    unchanged = sum(1 for r in results if r["status"] == "unchanged")
    failed = sum(1 for r in results if r["status"] == "failed")
    return {
        "requested": len(track_ids),
        "updated": updated,
        "unchanged": unchanged,
        "failed": failed,
        "results": results,
    }

"""Smartlist tools: create_smartlist.

Lexicon has no dedicated smartlist endpoint; a smartlist is a playlist of
type "3" carrying a `smartlist` rule set. Created via POST /v1/playlist.
"""

from __future__ import annotations

from typing import Any

from ..client import LexiconClient

_SMARTLIST_TYPE = "3"  # 1=folder, 2=playlist, 3=smartlist


async def create_smartlist(
    client: LexiconClient,
    name: str,
    rules: list[dict[str, Any]],
    *,
    match_all: bool = True,
    parent_id: int | None = None,
) -> dict[str, Any]:
    """Create a Lexicon smartlist from a rule set and return the created object.

    Each rule is ``{"field": ..., "operator": ..., "values": [...]}`` (e.g.
    ``{"field": "bpm", "operator": "NumberGreaterThan", "values": [120]}``).
    ``match_all=True`` means a track must satisfy every rule (AND); False is ANY
    (OR). The membership is evaluated by Lexicon, so this tool just plumbs the
    rules through — it does not interpret or validate the operator vocabulary.

    POST /v1/playlist returns only the new id, so we re-fetch and return the full
    smartlist (rules, resolved trackIds, etc.).
    """
    body: dict[str, Any] = {
        "name": name,
        "type": _SMARTLIST_TYPE,
        "smartlist": {"matchAll": match_all, "rules": list(rules)},
    }
    if parent_id is not None:
        body["parentId"] = parent_id

    created = await client.request("POST", "/v1/playlist", json=body)
    new_id = created["id"]
    data = await client.request("GET", "/v1/playlist", params={"id": new_id})
    return data["playlist"]

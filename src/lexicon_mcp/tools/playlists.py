"""Playlist tools: list_playlists, get_playlist_tracks."""

from __future__ import annotations

from typing import Any

from ..client import LexiconClient


async def list_playlists(client: LexiconClient) -> list[dict[str, Any]]:
    """Return every playlist and folder as a nested tree.

    Faithful to `GET /v1/playlists`: a list whose first element is the ROOT node,
    with folders (`type:"1"`) containing child `playlists` and playlists
    (`type:"2"`) as leaves. Track membership is NOT included here (the API does
    not provide counts in the tree) — use `get_playlist_tracks` for a playlist's
    contents.
    """
    data = await client.request("GET", "/v1/playlists")
    return data["playlists"]

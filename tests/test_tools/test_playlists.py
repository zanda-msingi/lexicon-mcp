"""Tests for playlist tools."""

import httpx

from lexicon_mcp.tools.playlists import list_playlists


async def test_list_playlists_returns_the_tree(make_client, load_fixture):
    tree = load_fixture("playlists.json")  # {"playlists": [ROOT...]}
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"data": tree})

    async with make_client(handler) as client:
        result = await list_playlists(client)

    assert seen["path"] == "/v1/playlists"
    # Faithful: the full nested folder/playlist tree comes back unchanged.
    assert result == tree["playlists"]
    assert result[0]["name"] == "ROOT"
    assert result[0]["playlists"][0]["name"] == "Example Folder"

"""Tests for list_playlists."""

import httpx

from lexicon_mcp.tools.playlists import list_playlists


def _tree_handler(tree):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/playlists"
        return httpx.Response(200, json={"data": tree})

    return handler


async def test_default_is_a_flat_list_with_paths_and_kinds(make_client, load_fixture):
    tree = load_fixture("playlists.json")

    async with make_client(_tree_handler(tree)) as client:
        rows = await list_playlists(client)

    assert rows == [
        {
            "id": 3,
            "name": "Example Folder",
            "path": "Example Folder",
            "kind": "folder",
            "parent_id": 2,
        },
        {
            "id": 4,
            "name": "Example Playlist A",
            "path": "Example Folder / Example Playlist A",
            "kind": "playlist",
            "parent_id": 3,
        },
        {
            "id": 5,
            "name": "Example Playlist B",
            "path": "Example Folder / Example Playlist B",
            "kind": "playlist",
            "parent_id": 3,
        },
        {
            "id": 6,
            "name": "Example Playlist C",
            "path": "Example Playlist C",
            "kind": "playlist",
            "parent_id": 2,
        },
        {
            "id": 7,
            "name": "Example Smartlist",
            "path": "Example Smartlist",
            "kind": "smartlist",
            "parent_id": 2,
        },
    ]


async def test_flat_list_omits_root_dates_and_nulls(make_client, load_fixture):
    tree = load_fixture("playlists.json")

    async with make_client(_tree_handler(tree)) as client:
        rows = await list_playlists(client)

    assert all(row["name"] != "ROOT" for row in rows)
    assert all(set(row) == {"id", "name", "path", "kind", "parent_id"} for row in rows)


async def test_unknown_type_is_passed_through_as_kind(make_client):
    tree = {
        "playlists": [
            {
                "id": 2,
                "name": "ROOT",
                "type": "1",
                "parentId": None,
                "playlists": [{"id": 9, "name": "Odd", "type": "7", "parentId": 2}],
            }
        ]
    }

    async with make_client(_tree_handler(tree)) as client:
        rows = await list_playlists(client)

    assert rows == [{"id": 9, "name": "Odd", "path": "Odd", "kind": "7", "parent_id": 2}]


async def test_tree_true_returns_the_nested_tree_unchanged(make_client, load_fixture):
    tree = load_fixture("playlists.json")  # {"playlists": [ROOT...]}

    async with make_client(_tree_handler(tree)) as client:
        result = await list_playlists(client, tree=True)

    # Faithful: the full nested folder/playlist tree comes back unchanged.
    assert result == tree["playlists"]
    assert result[0]["name"] == "ROOT"
    assert result[0]["playlists"][0]["name"] == "Example Folder"

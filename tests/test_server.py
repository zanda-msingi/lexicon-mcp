"""The MCP server wires up exactly the eight MVP tools."""

from lexicon_mcp.server import build_server

MVP_TOOLS = {
    "list_playlists",
    "get_playlist_tracks",
    "search_tracks",
    "get_track",
    "list_custom_tag_categories",
    "set_custom_tags",
    "bulk_apply_tags",
    "create_smartlist",
}


async def test_registers_all_eight_mvp_tools():
    server = build_server()
    tools = await server.list_tools()
    assert {t.name for t in tools} == MVP_TOOLS


async def test_every_tool_has_a_description():
    server = build_server()
    tools = await server.list_tools()
    assert all(t.description for t in tools)


async def test_search_tracks_exposes_filter_param():
    server = build_server()
    tools = {t.name: t for t in await server.list_tools()}
    props = tools["search_tracks"].inputSchema["properties"]
    assert "filter" in props

# lexicon-mcp

*An open-source [Model Context Protocol](https://modelcontextprotocol.io/) server for [Lexicon DJ](https://www.lexicondj.com/). Bring an LLM into your DJ library.*

> **Status:** v0.2. Thirteen tools, unit-tested against a mocked API and exercised against a real ~40,000-track library. Not yet on PyPI; install from source below. Requires Lexicon Essential or higher for the Local API.

Part of [dr-star](../README.md), the engineering shop of DiaspoRADiCAL Soundscapes.

## What this is

`lexicon-mcp` is a small local MCP server that wraps Lexicon DJ's REST API (`http://localhost:48624`) so any MCP-aware AI client (Claude in Cowork, Claude Desktop, Cursor, etc.) can read, query, and modify your DJ library through structured tool calls.

Once installed, you can have conversations like:

- *"Find every track in my West Africa playlist with energy above 7 and tag it with the 'Connection / The Struggle' family."*
- *"Build me a 90-minute warm-up set that starts in 6M and arcs through energy 3 to 6, leaning Afrobeat and amapiano."*
- *"Look at the last ten tracks I added and suggest mood and Undertow tags based on title, artist, and key."*

The server runs locally. Your library never leaves your machine. The AI client only sees what you ask it to look at.

## Why it exists

Library management software has been the unsexy plumbing of DJing for two decades. Lexicon broke ground by treating it as the main event, and then opened a Local API so developers can extend it. MCP is the matching standard on the AI side: a clean, language-agnostic way for an LLM to call structured tools.

Putting them together gives DJs something none of the major DJ apps offer out of the box: a real LLM collaborator that knows their actual library. Tag-by-conversation. Crate-by-conversation. Cue-prep-by-conversation. The library brain finally has a thinking partner.

## Architecture

```
┌──────────────────────┐    MCP     ┌──────────────────┐    HTTP    ┌──────────────────┐
│  MCP client          │ ◄────────► │  lexicon-mcp     │ ◄────────► │  Lexicon DJ      │
│  (Claude in Cowork,  │   stdio    │  (this server)   │  REST/JSON │  (localhost:     │
│  Cursor, etc.)       │            │                  │            │   48624)         │
└──────────────────────┘            └──────────────────┘            └──────────────────┘
```

Three moving parts. The MCP server is the thin one in the middle.

## Tool surface (v0.2)

Small, composable tools. The LLM combines them; the server never decides what a track should be tagged.

**Read the library**

| Tool | Purpose |
|---|---|
| `library_info` | One-call summary: track totals, bpm/key/energy/tag coverage, key notation in use, playlist counts, every tag with its track count. |
| `list_playlists` | Every folder, playlist and smartlist as flat `{id, name, path, kind, parent_id}` rows in Lexicon's order. `tree=True` for the raw nested tree. |
| `get_playlist_tracks` | A playlist's tracks in order, as compact records by default. `fields` picks exactly which fields; `full=True` returns everything (cues, tempo markers, source blobs). |
| `search_tracks` | Structured search: substring text, `>=`/`<=` comparisons, inclusive `"A-B"` ranges, AND across fields, sort, field selection. |
| `get_track` | Full record for one track. |
| `list_untagged_tracks` | Tracks with no custom tag, scoped to a playlist or paged across the whole library. The API cannot do this; the server scans for it. |

**Tag**

| Tool | Purpose |
|---|---|
| `list_custom_tag_categories` | The taxonomy currently defined in Lexicon. |
| `create_tag_category` | Add a category (e.g. "Undertow"). |
| `create_tag` | Add a tag to a category. |
| `set_custom_tags` | Replace a track's tags. Accepts ids or labels (`"Genre/Afro House"` or `"Afro House"`). |
| `bulk_apply_tags` | Merge the same tag(s) into many tracks, with a count check before any write. Ids or labels. |

**Curate**

| Tool | Purpose |
|---|---|
| `create_smartlist` | Create a Lexicon smartlist from rules. |
| `delete_playlist` | Delete a smartlist, or a playlist with `allow_playlist=True`. Never a folder. |

## Later (v0.3 and beyond)

- `add_tracks_to_playlist` / `remove_tracks_from_playlist` — the endpoints exist; "save this set as a crate".
- `find_similar_tracks` — by key, BPM proximity, tag overlap.
- `generate_set` — assemble a tracklist for a given duration, energy arc, and constraints.
- `write_tags_to_file` — trigger Lexicon's "write tags to file" on a track or set.
- `find_path_relinks` — propose path remappings for moved files.

## Configuration

Configuration is optional. With no config file at all, the server talks to `http://localhost:48624`. To override, put a `config.toml` in the working directory or point `LEXICON_MCP_CONFIG` at one:

```toml
# config.toml
[lexicon]
base_url = "http://localhost:48624"

[server]
log_level = "info"
```

The Local API currently has no authentication, so there is no key to configure. (Lexicon's docs say this will change; when it does, the client will grow an `api_key` setting.)

Before starting, the user enables the Local API in Lexicon: **Settings > Integrations > Local API > Enable**. (Requires Lexicon Essential or higher.)

## Install

From source (the only path until the package is on PyPI):

```bash
git clone https://github.com/zanda-msingi/dr-star.git
cd dr-star/lexicon-mcp
uv sync
uv run pytest      # 84 tests, no Lexicon needed
uv run lexicon-mcp # starts the stdio server; expects Lexicon running
```

Then register it with your MCP client (Claude Desktop, Claude Code, Cowork, Cursor). Point `--directory` at your checkout:

```json
{
  "mcpServers": {
    "lexicon": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/dr-star/lexicon-mcp", "lexicon-mcp"]
    }
  }
}
```

Once published, `pipx install lexicon-mcp` will make `"command": "lexicon-mcp"` enough on its own.

## Known limits (v0.2)

Honest notes from running it against a real library. Most are Lexicon API behaviour that the server surfaces rather than hides.

- **Search caps at 1000 records** server-side, whatever `limit` you pass, and there is no offset. `total` is always the true count, so narrow the filter when `total` exceeds what came back.
- **Search has no "untagged" filter.** The API's `tags=NONE` returns *every* track, so `search_tracks` refuses it. Use `list_untagged_tracks`, which scans for them.
- **Range syntax is particular.** `"bpm": "118-124"` works (inclusive). `">=118 <=124"` in one string silently matches nothing. Unanalysed tracks carry `bpm: 0`, so an upper-bound-only filter sweeps them in.
- **Key notation.** Lexicon stores keys in Open Key form (`1D` major, `6M` minor) and its key filter understands Camelot equivalents. `library_info` reports which notation a library uses.
- **Labels are unique library-wide, case-sensitively.** Lexicon enforces it. Label resolution matches exactly first and case-insensitively only when that is unique.
- **Full records are ~3 KB each.** `get_playlist_tracks(full=True)` and `get_track` return them; everything else is compact by default.

## Roadmap

- **v0.1.** Eight MVP tools. Documented. Tested against a real library. Done.
- **v0.2.** What real use asked for: compact payloads, flat playlist listing, `library_info`, taxonomy creation, tag labels, untagged listing, smartlist deletion. Done.
- **v0.3.** Playlist membership tools, similarity, set assembly, file-tag writing.
- **v0.4.** Optional support for other DJ library backends (Rekordbox via XML, Engine DJ via SQLite). Lexicon stays the primary because it's the universal converter.

## Project layout

```
lexicon-mcp/
├── pyproject.toml
├── README.md
├── docs/
│   └── upstream-api-issues.md   # pinned snapshot of known Lexicon API quirks
├── src/
│   └── lexicon_mcp/
│       ├── server.py      # FastMCP stdio entrypoint; registers the eight tools
│       ├── client.py      # thin async httpx client; unwraps envelopes, raises on errors
│       ├── config.py      # TOML config (tomllib), defaults work with no file
│       ├── errors.py      # LexiconConnectionError / LexiconAPIError
│       ├── guardrails.py  # unsafe-filter, dedupe, and bulk-write-ceiling checks
│       ├── models.py      # Pydantic shapes built from real responses
│       └── tools/         # one module per tool family
│           ├── playlists.py   # list_playlists, get_playlist_tracks, delete_playlist
│           ├── tracks.py      # search_tracks, get_track
│           ├── tags.py        # list_custom_tag_categories, create_*, set_custom_tags, bulk_apply_tags
│           ├── library.py     # library_info, list_untagged_tracks
│           └── smartlists.py  # create_smartlist
├── tests/                 # pytest, mocked API, sanitized fixtures
└── examples/
    ├── tag_a_playlist.md
    ├── generate_a_set.md
    └── bulk_tagging_recipe.md
```

## Design principles

- **Local-first.** The server never sends library data to a remote service. Privacy by default.
- **Composable.** Each tool does one job. The LLM composes them, not the server.
- **Honest about Lexicon tiers.** Some Lexicon features are paid (Custom Tags, the API itself). The README and tools fail loudly if a feature isn't available on the user's tier.
- **Library-shape-agnostic.** Don't assume the user organizes by genre, BPM, or anything else. The tools work on whatever the user has.

## Contributing

The repo opens with a small core, focused MVP, and an `examples/` folder. Contributions welcome for additional tool surfaces, recipe templates, and tested integrations with other MCP clients.

## License

[MIT](../LICENSE).

## Acknowledgements

Built originally to support DiaspoRADiCAL Soundscapes and [The DiaspoRADiO Show](https://www.xray.fm/shows/the-diasporadio-show), but designed from the start to work for any Lexicon user. Thanks to Lexicon's open API and the MCP team for making the bridge possible.

Special thanks to [`PhotonicVelocity/lexicon-python`](https://github.com/PhotonicVelocity/lexicon-python) (PyPI: [`lexicon-python`](https://pypi.org/project/lexicon-python/)). The published Lexicon API docs have no reference section, and that project's source — especially its [`docs/api-issues.md`](https://github.com/PhotonicVelocity/lexicon-python/blob/main/docs/api-issues.md) — was an invaluable **reference map** for the real endpoint shapes and the API's many quirks (a pinned snapshot lives in [`docs/upstream-api-issues.md`](./docs/upstream-api-issues.md)).

We wrote our own thin client rather than depending on it because lexicon-mcp is an **async MCP server**: we wanted an `httpx`-based, asyncio-native client that never blocks the MCP event loop, plus project-specific **safety guardrails** baked into the client (rejecting filters that would silently match the whole library, deduping playlist track ids, and a count-before-bulk-write ceiling). Where we find Lexicon API quirks not yet captured upstream, we send them back as pull requests.

# Project context for Claude Code

`lexicon-mcp` is an open-source MCP server that wraps [Lexicon DJ](https://www.lexicondj.com/)'s
Local API so any MCP-aware AI client can drive a DJ library through structured tool calls.
See [README.md](./README.md) for the design doc, tool surface, and known limits.

## Stack and conventions

- **Language:** Python 3.11+.
- **Package manager:** `uv` (preferred). `pip` works too.
- **MCP SDK:** the official Python MCP SDK (`mcp` on PyPI). A stdio-based server.
- **HTTP:** `httpx` for the Lexicon REST client. Async throughout.
- **Config:** TOML via `tomllib` (stdlib in 3.11+).
- **Testing:** `pytest`. The Lexicon API is mocked with an `httpx` `MockTransport`.
- **Lint/format:** `ruff` for both. Default config.
- **License:** MIT.

## Architecture

```
MCP client (Claude Desktop, Claude Code, Cursor) <-- MCP/stdio --> lexicon-mcp <-- HTTP/JSON --> Lexicon DJ (localhost:48624)
```

The MCP server is the thin layer in the middle. Don't put business logic here that
belongs in the LLM (e.g. "what tags to apply"). The server's job is plumbing:
faithful, well-typed access to Lexicon's data and operations.

## Tool surface

v0.3 in progress: fifteen tools under `src/lexicon_mcp/tools/`, one module per family, each with tests.

- Read: `library_info`, `list_playlists`, `get_playlist_tracks`, `search_tracks`, `get_track`, `list_untagged_tracks`
- Tag: `list_custom_tag_categories`, `create_tag_category`, `create_tag`, `set_custom_tags`, `bulk_apply_tags`
- Curate: `create_smartlist`, `create_playlist`, `add_tracks_to_playlist`, `delete_playlist`

Adding one? Follow `.claude/skills/adding-a-lexicon-tool/`. Keep each tool small and
composable; resist "smart" tools that take many shapes.

## Lexicon API setup

Enable the Local API in Lexicon: **Settings > Integrations > Local API > Enable**.
Default port `48624`. Requires Lexicon Essential or higher.

The published Lexicon API docs (`https://www.lexicondj.com/docs/developers/api`) have
no reference section. Real endpoint shapes and quirks are pinned in
[`docs/upstream-api-issues.md`](./docs/upstream-api-issues.md). Better still, hit the
live API directly during development. Contributors without a library can still run the
unit tests, which mock the API.

## Design principles (load-bearing)

- **Local-first.** The server never sends library data to a remote service. No telemetry.
- **Composable.** Each tool does one job. The LLM composes them, not the server.
- **Tier-honest.** Some Lexicon features are paid. Tools that require a feature fail
  loudly with a clear message if it isn't available, rather than silently degrading.
- **Library-shape-agnostic.** Don't assume any taxonomy or organization. The taxonomy
  lives in the user's Lexicon, not in this code.
- **Safe by default.** The Lexicon API has quirks where a bad filter silently matches
  the whole library. `guardrails.py` rejects those before they reach a bulk write.
  Extend it when you find a new one; don't work around it.

## Working agreement

- Every tool gets a test before it is wired into the server. Before writing a tool,
  hit the corresponding Lexicon endpoint manually (curl or httpie) and save a sample
  response under `discovery/` (gitignored). Build the Pydantic model from the real
  shape, not from the docs.
- Real captures stay local. `discovery/` is gitignored because it holds personal
  library data (gig names, track titles, file paths). Sanitized fixtures for tests
  live in `tests/fixtures/`.
- When you find a Lexicon API quirk not in `docs/upstream-api-issues.md`, add it there
  and send it upstream to `PhotonicVelocity/lexicon-python`.
- Keep commits small and focused. The commit log should read like documentation.

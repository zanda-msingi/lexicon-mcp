---
name: adding-a-lexicon-tool
description: Use when a new tool is going into lexicon-mcp, when a v0.3 backlog item is being picked up, when a Lexicon endpoint needs an MCP surface, or when a change touches a tool's parameters or its registration in the server.
---

# Adding a Lexicon tool

## Overview

One tool, one loop, one commit. The loop held for seven tools in a row with no
regression. `superpowers:test-driven-development` is the generic red-green
discipline; this is the lexicon-mcp loop around it. The library is left as found.

## When to use

- A new tool is going into `src/lexicon_mcp/tools/`.
- An existing tool gains or changes a parameter (its schema test moves with it).
- A v0.3 item is starting (`run_lexicon_command`, `now_playing`, playlist membership).

Not for docs-only changes, taxonomy design (Custom Tags and the vault, never
code), or deciding *which* tags to apply. That is the LLM's job.

## Steps

1. **Probe the real endpoint first.** Hit it manually (`curl`/`httpie`) and save
   the response under `discovery/` (gitignored; personal library data). Build
   the Pydantic model and the test's expected shape from the real payload, not
   from the OpenAPI spec — the spec lies in places (fugee ledger).
2. **Failing test first.** Add `tests/test_tools/<tool>.py`, named like its
   neighbours. Use the `make_client` fixture, the httpx `MockTransport` handler
   that fakes the Lexicon API. Never a new fixture. Assert the shape from step 1.
3. **Run pytest and read the failure.** It must fail because the function is
   missing or returns the wrong shape, not from a typo, an import, or the
   fixture. Fix anything else first.
4. **Implement** in `src/lexicon_mcp/tools/<family>.py` (`playlists`, `tracks`,
   `tags`, `smartlists`, `library`). Minimal code to go green. Plumbing only:
   faithful, typed access to what Lexicon returns.
5. **Register in `server.py`** and add a server-level test asserting the tool's
   parameter schema. Pytest again: both green, nothing else red.
6. **`ruff format`, then `ruff check`.** Fix what it reports.
7. **Live check against the real library** through the running server. Any
   object the check creates (category, tag, smartlist) gets a `zz-` name and is
   deleted in the same run. Re-read to prove the library is as found.
8. **One commit for this tool.** The message reads like documentation: what,
   why, and the measured numbers from the live check (payload size, timing,
   counts).

## Quick reference

| Step | Where / what |
|---|---|
| Probe | `curl` the endpoint, save under `discovery/`, model from the real shape |
| Test | `tests/test_tools/<tool>.py`, `make_client` |
| Code | `src/lexicon_mcp/tools/<family>.py` |
| Registration | `server.py` plus schema test |
| Lint | `ruff format`, `ruff check` |
| Live | `zz-` objects, deleted same run |
| Commit | one per tool, numbers in the message |

## Common mistakes

- **Modelling from the spec, not the wire.** The captured OpenAPI spec is wrong
  in places and wrappers differ by endpoint. Probe first; only live settles it.
- **Code before test.** It passes for the wrong reason; step 3 catches this.
- **A fresh mock instead of `make_client`.** Two fakes drift; the next tool
  inherits the drift.
- **Skipping the schema test.** Unit tests pass while the tool is unregistered
  or its parameters change silently under the client.
- **Leaving a `zz-` object behind.** Delete in the same run; re-read to prove it.
- **Several tools in one commit.** The log stops being documentation.

"""TOML config loading (stdlib ``tomllib``).

Config is intentionally tiny. The taxonomy lives in the user's Lexicon, not here.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "http://localhost:48624"


@dataclass(frozen=True)
class Config:
    base_url: str = DEFAULT_BASE_URL
    log_level: str = "info"


def load_config(path: str | Path | None = None) -> Config:
    """Load config from a TOML file, falling back to defaults.

    Lookup order when ``path`` is None: ``$LEXICON_MCP_CONFIG``, then ``./config.toml``.
    A missing file (or missing keys) yields defaults — the server runs out of the
    box against a local Lexicon with no config at all.
    """
    if path is None:
        env = os.environ.get("LEXICON_MCP_CONFIG")
        path = Path(env) if env else Path("config.toml")
    else:
        path = Path(path)

    if not path.is_file():
        return Config()

    with path.open("rb") as fh:
        raw = tomllib.load(fh)

    lexicon = raw.get("lexicon", {})
    server = raw.get("server", {})
    defaults = Config()
    return Config(
        base_url=lexicon.get("base_url", defaults.base_url),
        log_level=server.get("log_level", defaults.log_level),
    )

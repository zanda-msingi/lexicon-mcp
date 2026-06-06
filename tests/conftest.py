"""Shared test helpers.

`make_client` builds a real LexiconClient wired to an httpx MockTransport, so
tool/client tests exercise the genuine request path with no network.
`load_fixture` reads sanitized API-shaped JSON from tests/fixtures/.
"""

import json
from pathlib import Path

import httpx
import pytest

from lexicon_mcp.client import LexiconClient

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(name: str):
        return json.loads((FIXTURES / name).read_text())

    return _load


@pytest.fixture
def make_client():
    def _make(handler):
        return LexiconClient(transport=httpx.MockTransport(handler))

    return _make

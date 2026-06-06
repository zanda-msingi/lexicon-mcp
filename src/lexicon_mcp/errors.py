"""Exception types for lexicon-mcp.

Errors are surfaced to the calling LLM/user, so messages are written to be
actionable, not just diagnostic (tier-honest, fail-loudly design principle).
"""

from __future__ import annotations


class LexiconError(Exception):
    """Base class for all lexicon-mcp errors."""


class LexiconConnectionError(LexiconError):
    """Could not reach the Lexicon Local API at all."""


class LexiconAPIError(LexiconError):
    """The Lexicon API returned an error envelope (`{message, errorCode}`)."""

    def __init__(
        self, message: str, error_code: int | None = None, status_code: int | None = None
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(message)

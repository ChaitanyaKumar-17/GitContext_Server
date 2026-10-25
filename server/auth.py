"""
auth.py
~~~~~~~
Bearer-token verification helper.

Used by main.py to protect every MCP endpoint.
The expected token is read from the MCP_BEARER_TOKEN environment variable.
"""

import logging
import os

log = logging.getLogger(__name__)


def verify_bearer_token(authorization_header: str | None) -> bool:
    """
    Return True if the Authorization header contains the correct Bearer token.
    Returns False (and logs a warning) for missing or incorrect tokens.
    """
    expected = os.getenv("MCP_BEARER_TOKEN", "")
    if not expected:
        log.warning(
            "MCP_BEARER_TOKEN is not set — all requests will be rejected. "
            "Set it in your .env file."
        )
        return False

    if not authorization_header:
        log.warning("Request rejected: missing Authorization header.")
        return False

    parts = authorization_header.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        log.warning("Request rejected: malformed Authorization header.")
        return False

    token = parts[1].strip()
    if token != expected:
        log.warning("Request rejected: invalid Bearer token.")
        return False

    return True

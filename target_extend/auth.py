"""Authentication helpers for target-extend."""

from __future__ import annotations

import base64
from typing import Any, Dict


class ExtendAuth:
    """Build Extend Commerce authentication headers from target config."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize authentication from username and password config."""
        self.username = config["username"]
        self.password = config["password"]

    @property
    def auth_header(self) -> str:
        """Return the ExtendBasicAuthorization header value."""
        token = f"{self.username}:{self.password}".encode("utf-8")
        encoded = base64.b64encode(token).decode("ascii")
        return f"Basic {encoded}"

    @property
    def headers(self) -> Dict[str, str]:
        """Return HTTP headers required by Extend."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "ExtendBasicAuthorization": self.auth_header,
        }

"""Authentication models for MCP Agent Cloud CLI."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class UserCredentials:
    """User authentication credentials and identity information."""

    # Authentication
    api_key: str = field(repr=False)
    token_expires_at: Optional[datetime] = None

    # Identity
    username: Optional[str] = None
    email: Optional[str] = None

    @property
    def is_token_expired(self) -> bool:
        """Check if the token is expired."""
        if not self.token_expires_at:
            return False
        return datetime.now() > self.token_expires_at

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "api_key": self.api_key,
            "username": self.username,
            "email": self.email,
        }

        if self.token_expires_at:
            result["token_expires_at"] = self.token_expires_at.isoformat()

        return result

    @classmethod
    def from_dict(cls, data: dict) -> "UserCredentials":
        """Create from dictionary loaded from JSON."""

        token_expires_at = None
        if "token_expires_at" in data:
            token_expires_at = datetime.fromisoformat(data["token_expires_at"])

        return cls(
            api_key=data["api_key"],
            token_expires_at=token_expires_at,
            username=data.get("username"),
            email=data.get("email"),
        )

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "UserCredentials":
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

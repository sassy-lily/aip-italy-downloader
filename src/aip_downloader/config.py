"""Configuration loading. The single place that reads the environment.

Centralising env access keeps secrets out of the rest of the code and makes the
whole app configurable from one typed object that tests can construct directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from .politeness import PolitenessPolicy

DEFAULT_BASE_URL = "https://www.enav.it"
DEFAULT_OUTPUT_DIR = "./downloads"


@dataclass
class Settings:
    """Resolved runtime configuration."""

    base_url: str
    output_dir: Path
    user: str
    password: str
    politeness: PolitenessPolicy = field(default_factory=PolitenessPolicy)
    session_path: Path = field(default_factory=lambda: Path("storage_state.json"))

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        """Build settings from the environment, loading a local .env first.

        Pass ``env`` explicitly in tests to avoid touching the real process env.
        """
        if env is None:
            load_dotenv()  # populates os.environ from .env if present
            env = dict(os.environ)
        return cls(
            base_url=env.get("AIP_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            output_dir=Path(env.get("AIP_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)),
            user=env.get("AIP_USER", ""),
            password=env.get("AIP_PASS", ""),
            session_path=Path(env.get("AIP_SESSION_PATH", "storage_state.json")),
        )

    def require_credentials(self) -> None:
        """Raise if credentials are missing (needed for live runs, not tests)."""
        if not self.user or not self.password:
            raise ValueError(
                "AIP_USER and AIP_PASS must be set (copy .env.example to .env)."
            )

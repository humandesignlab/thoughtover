"""Configuration loaded from the environment / a local .env file.

Every secret and model id lives here. Values are optional at load time so the
CLI can start without a fully populated .env; each command then calls
``Config.require(...)`` to validate only the keys it actually needs and fail
with a clear message otherwise.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"


class MissingConfigError(RuntimeError):
    """Raised when a command needs a key that is absent from the environment."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        keys = ", ".join(missing)
        super().__init__(
            f"Missing required configuration: {keys}.\n"
            "Copy .env.example to .env and fill in the value(s) above."
        )


class Config(BaseSettings):
    """Typed view of the .env file. Model ids carry verified-current defaults."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Vision, the "seeing": Google Gemini
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.5-flash", alias="GEMINI_MODEL")
    gemini_video_fps: float = Field(default=4.0, alias="GEMINI_VIDEO_FPS")

    # Writing, the persona: Anthropic Claude
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-opus-4-8", alias="ANTHROPIC_MODEL")

    # Voice, the speaking: ElevenLabs cloned voice
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str | None = Field(default=None, alias="ELEVENLABS_VOICE_ID")
    elevenlabs_model: str = Field(default="eleven_multilingual_v2", alias="ELEVENLABS_MODEL")

    # Output and mixing
    narration_duck_db: float = Field(default=-12.0, alias="NARRATION_DUCK_DB")

    def require(self, *fields: str) -> None:
        """Validate that the given fields are present and non-empty.

        ``fields`` are python attribute names; the error reports their .env
        variable names so the message points at what to set.
        """
        missing: list[str] = []
        for name in fields:
            value = getattr(self, name)
            if value is None or (isinstance(value, str) and not value.strip()):
                alias = type(self).model_fields[name].alias or name.upper()
                missing.append(alias)
        if missing:
            raise MissingConfigError(missing)


def load_config() -> Config:
    """Load configuration from the environment and the repo-local .env file."""
    return Config()

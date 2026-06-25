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
    elevenlabs_voice_id_es: str | None = Field(
        default=None, alias="ELEVENLABS_VOICE_ID_ES"
    )
    elevenlabs_model: str = Field(default="eleven_multilingual_v2", alias="ELEVENLABS_MODEL")
    narration_speed: float = Field(default=1.0, alias="NARRATION_SPEED")
    narration_stability: float = Field(default=0.5, alias="NARRATION_STABILITY")
    narration_similarity: float = Field(default=0.75, alias="NARRATION_SIMILARITY")
    narration_style: float = Field(default=0.0, alias="NARRATION_STYLE")
    narration_speaker_boost: bool = Field(default=True, alias="NARRATION_SPEAKER_BOOST")

    # Output and mixing
    narration_duck_db: float = Field(default=-8.0, alias="NARRATION_DUCK_DB")
    narration_gain_db: float = Field(default=0.0, alias="NARRATION_GAIN_DB")
    narration_reaction_lag: float = Field(default=0.8, alias="NARRATION_REACTION_LAG")
    narration_duck_fade: float = Field(default=0.4, alias="NARRATION_DUCK_FADE")

    # Sound design (mix-stage; tune freely and re-render with --reuse-voices)
    narration_inner_voice: bool = Field(default=True, alias="NARRATION_INNER_VOICE")
    narration_inner_voice_reverb: float = Field(
        default=0.15, alias="NARRATION_INNER_VOICE_REVERB"
    )
    ambience_highpass_hz: float = Field(default=50.0, alias="AMBIENCE_HIGHPASS_HZ")
    ambience_carve_db: float = Field(default=-2.5, alias="AMBIENCE_CARVE_DB")
    loudnorm: bool = Field(default=True, alias="LOUDNORM")
    output_lufs: float = Field(default=-14.0, alias="OUTPUT_LUFS")
    output_true_peak: float = Field(default=-1.0, alias="OUTPUT_TRUE_PEAK")

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

    def voice_id_for(self, lang: str) -> str:
        """Return the ElevenLabs voice id for ``lang``, validating it is configured."""
        if lang == "es":
            self.require("elevenlabs_voice_id_es")
            return self.elevenlabs_voice_id_es  # type: ignore[return-value]
        self.require("elevenlabs_voice_id")
        return self.elevenlabs_voice_id  # type: ignore[return-value]


def load_config() -> Config:
    """Load configuration from the environment and the repo-local .env file."""
    return Config()

from enum import Enum

from pydantic import BaseModel, Field

from .. import i18n


class Level(str, Enum):
    INFO = "INFO"
    SUSPICIOUS = "SUSPICIOUS"
    LIKELY_FAKE = "LIKELY_FAKE"
    UNVERIFIED = "UNVERIFIED"

    def label(self, lang: str | None = None) -> str:
        return i18n.t(f"level.{self.value}", lang=lang)


class Finding(BaseModel):
    rule_id: str
    level: Level
    score: float = Field(ge=0.0, le=1.0, default=0.0)
    explanation: str
    evidence: list[str] = Field(default_factory=list)
    recommendation: str = ""
    device_index: int | None = None


class Assessment(BaseModel):
    """Per-device verdict: level from the weighted sum of fired rules."""

    device_index: int
    level: Level
    score: float = Field(ge=0.0, le=1.0, default=0.0)
    rule_ids: list[str] = Field(default_factory=list)

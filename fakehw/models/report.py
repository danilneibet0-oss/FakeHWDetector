from datetime import datetime

from pydantic import BaseModel, Field

from .device import DeviceRecord
from .finding import Assessment, Finding


class Report(BaseModel):
    generated_at: datetime
    devices: list[DeviceRecord] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    assessments: list[Assessment] = Field(default_factory=list)
    kb_versions: dict[str, str] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, indent=2)

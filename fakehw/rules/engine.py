"""Rule model, YAML loader and evaluation engine."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError, field_validator, model_validator

from .. import i18n
from ..kb.cpu_tables import CpuTables
from ..kb.gpu_refs import GpuRefs
from ..kb.pci_ids import PciIds
from ..kb.usb_ids import UsbIds
from ..models.device import DeviceClass, DeviceRecord
from ..models.finding import Assessment, Finding, Level
from . import dsl, scoring
from .signals import compute_signals

BUILTIN_RULES_DIR = Path(__file__).parent / "rules"


class RuleLoadError(Exception):
    pass


class LocalizedText(RootModel[dict[str, str]]):
    """Plain string means English; a mapping gives per-language text. 'en' is required."""

    @model_validator(mode="before")
    @classmethod
    def _from_str(cls, v):
        return {"en": v} if isinstance(v, str) else v

    @field_validator("root")
    @classmethod
    def _needs_en(cls, v):
        if "en" not in v:
            raise ValueError("'en' text is required")
        return v

    def get(self, lang: str = "en") -> str:
        return self.root.get(lang) or self.root["en"]


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    applies_to: list[DeviceClass] = Field(min_length=1)
    signals: list[str]
    condition: str
    weight: float = Field(ge=0.0, le=1.0)
    false_positive_risk: Literal["low", "medium", "high"]
    explanation: LocalizedText
    recommendation: LocalizedText

    @model_validator(mode="after")
    def _check_condition(self):
        try:
            names = dsl.signal_names(self.condition)
        except dsl.ConditionError as e:
            raise ValueError(f"invalid condition: {e}") from e
        undeclared = names - set(self.signals)
        if undeclared:
            raise ValueError(f"condition uses undeclared signals: {sorted(undeclared)}")
        return self


def load_rules(directory: Path | None = None) -> list[Rule]:
    directory = Path(directory) if directory is not None else BUILTIN_RULES_DIR
    if not directory.is_dir():
        raise RuleLoadError(f"rules directory not found: {directory}")
    rules: list[Rule] = []
    seen: dict[str, Path] = {}
    for path in sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")]):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            rule = Rule.model_validate(data)
        except (yaml.YAMLError, ValidationError, OSError) as e:
            raise RuleLoadError(f"{path.name}: {e}") from e
        if rule.id in seen:
            raise RuleLoadError(f"duplicate rule id {rule.id!r} in {path.name} and {seen[rule.id].name}")
        seen[rule.id] = path
        rules.append(rule)
    return rules


class RuleState(str, Enum):
    FIRED = "fired"
    NOT_FIRED = "not_fired"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class RuleResult:
    rule: Rule
    state: RuleState
    signals: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvalContext:
    pci: PciIds | None
    usb: UsbIds | None
    cpu_tables: CpuTables | None
    virtualization: str = "unknown"
    gpu_refs: GpuRefs | None = None


SignalProvider = Callable[[DeviceRecord, EvalContext], dict[str, Any]]


class Engine:
    def __init__(
        self,
        rules: list[Rule],
        ctx: EvalContext,
        lang: str = "en",
        signal_provider: SignalProvider = compute_signals,
    ):
        self.rules = rules
        self.ctx = ctx
        self.lang = lang
        self.signal_provider = signal_provider

    def evaluate(self, device: DeviceRecord) -> list[RuleResult]:
        applicable = [r for r in self.rules if device.device_class in r.applies_to]
        if not applicable:
            return []
        available = self.signal_provider(device, self.ctx)
        results = []
        for rule in applicable:
            values = {name: available.get(name) for name in rule.signals}
            used = dsl.signal_names(rule.condition)
            missing = [n for n in rule.signals if n in used and values[n] is None]
            if missing:
                results.append(RuleResult(rule, RuleState.UNVERIFIED, values, missing))
                continue
            try:
                fired = dsl.evaluate(rule.condition, values)
            except dsl.ConditionError:
                results.append(RuleResult(rule, RuleState.UNVERIFIED, values, sorted(used)))
                continue
            results.append(RuleResult(rule, RuleState.FIRED if fired else RuleState.NOT_FIRED, values))
        return results

    def run(self, devices: list[DeviceRecord]) -> tuple[list[Finding], list[Assessment]]:
        findings: list[Finding] = []
        assessments: list[Assessment] = []
        for index, device in enumerate(devices):
            confidence = scoring.confidence_for(device.device_class, self.ctx.virtualization)
            contributions: list[float] = []
            fired_ids: list[str] = []
            checked = False
            for res in self.evaluate(device):
                if res.state is RuleState.UNVERIFIED:
                    findings.append(self._unverified(res, index))
                    continue
                checked = True
                if res.state is RuleState.FIRED:
                    c = scoring.contribution(res.rule.weight, confidence)
                    contributions.append(c)
                    fired_ids.append(res.rule.id)
                    findings.append(self._fired(res, index, c, confidence))
            score = round(scoring.total(contributions), 4)
            if fired_ids:
                level = scoring.level_for(score)
            else:
                level = Level.INFO if checked else Level.UNVERIFIED
            assessments.append(Assessment(device_index=index, level=level, score=score, rule_ids=fired_ids))
        return findings, assessments

    def _fired(self, res: RuleResult, index: int, contribution: float, confidence: float) -> Finding:
        t = lambda key, **kw: i18n.t(key, lang=self.lang, **kw)  # noqa: E731
        used = dsl.signal_names(res.rule.condition)
        basis = ", ".join(f"{n}={res.signals[n]}" for n in res.rule.signals if n in used)
        explanation = f"{res.rule.explanation.get(self.lang)} {t('basis')}: {basis}. {t('disclaimer')}"
        evidence = [f"{n}={res.signals[n]}" for n in res.rule.signals if n in used]
        if confidence != 1.0:
            evidence.append(t("evidence.virtualization", state=self.ctx.virtualization, factor=confidence))
        return Finding(
            rule_id=res.rule.id, level=scoring.level_for(contribution), score=round(contribution, 4),
            explanation=explanation, evidence=evidence,
            recommendation=res.rule.recommendation.get(self.lang), device_index=index,
        )

    def _unverified(self, res: RuleResult, index: int) -> Finding:
        text = i18n.t("finding.unverified", lang=self.lang, missing=", ".join(res.missing))
        return Finding(
            rule_id=res.rule.id, level=Level.UNVERIFIED, score=0.0, explanation=text,
            evidence=[f"{n}=unknown" for n in res.missing], device_index=index,
        )

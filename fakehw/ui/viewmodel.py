"""Qt-free view model: rows for the device table and HTML for the detail panel (unit-testable)."""

from dataclasses import dataclass, field
from html import escape

from .. import i18n
from ..models.device import DeviceClass, DeviceRecord
from ..models.finding import Finding, Level
from ..models.report import Report

_COLORS = {
    Level.INFO: "#d4efdc",
    Level.SUSPICIOUS: "#ffe7a3",
    Level.LIKELY_FAKE: "#f5b5ae",
    Level.UNVERIFIED: "#dadde3",
}
# Symbols repeat the level so colour is never the only cue.
_SYMBOLS = {Level.INFO: "●", Level.SUSPICIOUS: "▲", Level.LIKELY_FAKE: "✖", Level.UNVERIFIED: "?"}


def level_color(level: Level) -> str:
    return _COLORS[level]


def level_symbol(level: Level) -> str:
    return _SYMBOLS[level]


def level_label(level: Level) -> str:
    return level.label()


def class_label(cls: DeviceClass) -> str:
    return i18n.t(f"ui.class.{cls.value}")


def virtualization_text(state: str) -> str:
    return i18n.t(f"ui.virt.{state}")


@dataclass
class DeviceRow:
    index: int
    device: DeviceRecord
    level: Level
    score: float
    name: str
    ids: str
    note: str
    findings: list[Finding] = field(default_factory=list)
    unverified: list[Finding] = field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        """Anything worth a second look: a triggered rule or a level other than plain information."""
        return bool(self.findings) or self.level is not Level.INFO


def _gb(value: str | None, decimal: bool) -> str:
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    return f"{round(n / (1000**3 if decimal else 1024**3))} GB"


def display_name(d: DeviceRecord) -> str:
    s, r = d.strings, d.raw_ids
    cls = d.device_class
    if cls is DeviceClass.RAM:
        base = " ".join(x for x in (s.get("manufacturer"), s.get("part_number")) if x)
        size = _gb(r.get("capacity_bytes"), decimal=False)
        return f"{base} ({size})" if base and size else base or size or d.source
    if cls is DeviceClass.STORAGE:
        size = _gb(r.get("size_bytes"), decimal=True)
        model = s.get("model") or d.source
        return f"{model} ({size})" if size else model
    for key in ("name", "model", "brand", "dxgi_description", "nvml_name"):
        if s.get(key):
            return s[key]
    return f"{class_label(cls)} ({d.source})"


def ids_summary(d: DeviceRecord) -> str:
    r = d.raw_ids
    cls = d.device_class
    if cls in (DeviceClass.PCI, DeviceClass.GPU) and "vendor_id" in r:
        base = f"{r['vendor_id']}:{r.get('device_id', '????')}"
        sv, sd = r.get("subsys_vendor_id"), r.get("subsys_device_id")
        return f"{base} ({sv}:{sd})" if sv and sd and (sv, sd) != ("0000", "0000") else base
    if cls is DeviceClass.USB and "vendor_id" in r:
        return f"{r['vendor_id']}:{r.get('product_id', '????')}"
    if cls is DeviceClass.CPU and "family" in r:
        return f"{r['family']}/{r.get('model', '?')}/{r.get('stepping', '?')}"
    if cls is DeviceClass.RAM:
        return r.get("manufacturer_code", "")
    if cls is DeviceClass.STORAGE:
        vid = r.get("nvme_vid")
        return f"{r.get('bus_type', '')} {vid}".strip() if vid else r.get("bus_type", "")
    return ""


def _note(d: DeviceRecord) -> str:
    parts = []
    if d.privilege_needed:
        parts.append(i18n.t("ui.notes.privilege"))
    extra = len(d.errors) - (1 if d.privilege_needed and d.errors else 0)
    if extra > 0:
        parts.append(i18n.t("ui.notes.errors", n=extra))
    return "; ".join(parts)


def build_rows(report: Report) -> list[DeviceRow]:
    by_device: dict[int, list[Finding]] = {}
    for f in report.findings:
        if f.device_index is not None:
            by_device.setdefault(f.device_index, []).append(f)
    assess = {a.device_index: a for a in report.assessments}
    rows = []
    for i, d in enumerate(report.devices):
        a = assess.get(i)
        found = by_device.get(i, [])
        rows.append(DeviceRow(
            index=i, device=d,
            level=a.level if a else Level.UNVERIFIED, score=a.score if a else 0.0,
            name=display_name(d), ids=ids_summary(d), note=_note(d),
            findings=[f for f in found if f.level is not Level.UNVERIFIED],
            unverified=[f for f in found if f.level is Level.UNVERIFIED],
        ))
    return rows


def filter_rows(rows: list[DeviceRow], only_findings: bool) -> list[DeviceRow]:
    return [r for r in rows if r.has_findings] if only_findings else list(rows)


def _e(text: object) -> str:
    return escape(str(text), quote=True)


def _table(pairs: dict[str, str]) -> str:
    body = "".join(f"<tr><td><b>{_e(k)}</b></td><td>{_e(v)}</td></tr>" for k, v in sorted(pairs.items()))
    return f"<table cellspacing='4'>{body}</table>"


def detail_html(row: DeviceRow) -> str:
    t = i18n.t
    d = row.device
    out = [f"<h3>{_e(row.name)}</h3>",
           f"<p>{_e(class_label(d.device_class))} · {t('ui.detail.source')}: {_e(d.source)}</p>",
           f"<p><b>{t('ui.detail.verdict')}:</b> {level_symbol(row.level)} {_e(level_label(row.level))} "
           f"({t('ui.detail.score')} {row.score:.2f})</p>"]

    out.append(f"<h4>{t('ui.detail.findings')}</h4>")
    if row.findings:
        for f in row.findings:
            out.append(f"<p><b>{_e(f.rule_id)}</b> — {_e(level_label(f.level))} ({f.score:.2f})<br>{_e(f.explanation)}</p>")
            if f.evidence:
                out.append(f"<p>{t('ui.detail.evidence')}:</p><ul>" + "".join(f"<li>{_e(x)}</li>" for x in f.evidence) + "</ul>")
            if f.recommendation:
                out.append(f"<p><b>{t('ui.detail.recommendation')}:</b> {_e(f.recommendation)}</p>")
    else:
        out.append(f"<p>{t('ui.detail.no_findings')}</p>")

    if row.unverified:
        out.append(f"<h4>{t('ui.detail.unverified')}</h4><ul>"
                   + "".join(f"<li><b>{_e(f.rule_id)}</b> — {_e(f.explanation)}</li>" for f in row.unverified) + "</ul>")

    if d.raw_ids:
        out.append(f"<h4>{t('ui.detail.ids')}</h4>{_table(d.raw_ids)}")
    if d.strings:
        out.append(f"<h4>{t('ui.detail.strings')}</h4>{_table(d.strings)}")
    if d.privilege_needed:
        out.append(f"<p>{t('ui.detail.privilege')}</p>")
    if d.errors:
        out.append(f"<h4>{t('ui.detail.problems')}</h4><ul>" + "".join(f"<li>{_e(x)}</li>" for x in d.errors) + "</ul>")
    return "".join(out)

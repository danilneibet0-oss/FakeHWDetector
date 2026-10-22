"""Markdown report. Same input gives the same output (no clock, no randomness)."""

import re
from pathlib import Path

from .. import branding, i18n
from ..models.report import Report
from ..rules.scoring import virtualization_state
from ..ui import viewmodel as vm  # Qt-free: rows, names, level labels


def _md(text: object) -> str:
    """Escape text for a Markdown table cell or paragraph."""
    s = re.sub(r"\s+", " ", str(text)).strip()
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_\[\]|])", r"\\\1", s)


def render_markdown(report: Report, lang: str | None = None) -> str:
    with i18n.use_language(lang or i18n.get_language()):
        return _render(report)


def _render(report: Report) -> str:
    t = i18n.t
    rows = vm.build_rows(report)
    kb = report.kb_versions
    virt = vm.virtualization_text(virtualization_state(report.devices))
    out = [
        f"# {branding.APP_NAME}",
        f"*{branding.TAGLINE}*",
        "",
        f"- {t('report.generated')}: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S %Z').strip()}",
        f"- {t('ui.status.kb', pci=kb.get('pci', '?'), usb=kb.get('usb', '?'))}",
        f"- {t('ui.status.virtualization', state=_md(virt))}",
        f"- {t('report.privacy')}",
        "",
        f"> {t('disclaimer')}",
        "",
        f"## {t('report.summary')}",
        "",
        "| " + " | ".join(t(f"ui.col.{c}") for c in ("level", "class", "name", "ids", "score", "notes")) + " |",
        "|---|---|---|---|---:|---|",
    ]
    for r in rows:
        out.append("| " + " | ".join([
            f"{vm.level_symbol(r.level)} {_md(vm.level_label(r.level))}",
            _md(vm.class_label(r.device.device_class)), _md(r.name), _md(r.ids), f"{r.score:.2f}", _md(r.note),
        ]) + " |")

    out += ["", f"## {t('report.details')}"]
    for r in rows:
        out += ["", f"### {r.index + 1}. {_md(r.name)}", "",
                f"- {t('ui.col.class')}: {_md(vm.class_label(r.device.device_class))}; {t('ui.detail.source')}: `{r.device.source}`",
                f"- {t('ui.detail.verdict')}: {vm.level_symbol(r.level)} {_md(vm.level_label(r.level))} "
                f"({t('ui.detail.score')} {r.score:.2f})"]
        if r.findings:
            out += ["", f"**{t('ui.detail.findings')}**"]
            for f in r.findings:
                out += ["", f"- `{f.rule_id}` — {_md(vm.level_label(f.level))} ({f.score:.2f})", f"  {_md(f.explanation)}"]
                for e in f.evidence:
                    out.append(f"  - {t('ui.detail.evidence')}: `{e}`")
                if f.recommendation:
                    out.append(f"  - **{t('ui.detail.recommendation')}:** {_md(f.recommendation)}")
        else:
            out += ["", t("ui.detail.no_findings")]
        if r.unverified:
            out += ["", f"**{t('ui.detail.unverified')}**", ""]
            out += [f"- `{f.rule_id}` — {_md(f.explanation)}" for f in r.unverified]
        if r.device.raw_ids:
            out += ["", f"{t('ui.detail.ids')}: " + ", ".join(f"`{k}={v}`" for k, v in sorted(r.device.raw_ids.items()))]
        if r.device.privilege_needed:
            out += ["", _md(t("ui.detail.privilege"))]
        if r.device.errors:
            out += ["", f"{t('ui.detail.problems')}:"] + [f"- {_md(e)}" for e in r.device.errors]
    return "\n".join(out) + "\n"


def export_markdown(report: Report, path: str | Path, lang: str | None = None) -> None:
    Path(path).write_text(render_markdown(report, lang), encoding="utf-8")

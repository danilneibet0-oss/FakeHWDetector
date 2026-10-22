"""Qt-free rendering of the "About this computer" tab: titled sections of (label, value) rows, HTML and plain text."""

from dataclasses import dataclass, field
from datetime import datetime
from html import escape

from .. import branding, i18n
from ..collectors._placeholder import names_match
from ..collectors.powershell import as_list

# SMBIOS type 17 "Memory Type" codes (DMTF DSP0134). Other codes (Other, Unknown, ...) show no type at all.
SMBIOS_MEMORY_TYPES = {
    18: "DDR", 19: "DDR2", 24: "DDR3", 26: "DDR4", 27: "LPDDR", 28: "LPDDR2", 29: "LPDDR3", 30: "LPDDR4",
    34: "DDR5", 35: "LPDDR5",
}


@dataclass
class Section:
    title: str
    rows: list[tuple[str, str]] = field(default_factory=list)

    def add(self, label: str, value: str) -> None:
        if value:
            self.rows.append((label, value))


def _text(v: object) -> str:
    return str(v).strip() if v is not None else ""


def _int(v: object) -> int | None:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _join(*parts: str, sep: str = ", ") -> str:
    return sep.join(p for p in parts if p)


def _num(x: float) -> str:
    s = f"{x:.0f}" if x >= 100 else f"{x:.1f}".rstrip("0").rstrip(".")
    return s.replace(".", ",") if i18n.get_language() == "ru" else s


def size(n: object, decimal: bool = False) -> str:
    """Bytes as KB/MB/GB/TB: decimal for drives (as labelled on the box), binary for memory and volumes."""
    b = _int(n)
    if b is None or b <= 0:
        return ""
    step = 1000 if decimal else 1024
    v = b / step
    for unit in ("kb", "mb", "gb", "tb"):
        if v < step or unit == "tb":
            return f"{_num(v)} {i18n.t('unit.' + unit)}"
        v /= step
    return ""  # unreachable


def _mhz(v: object) -> str:
    n = _int(v)
    return f"{n} {i18n.t('unit.mhz')}" if n else ""


def _date(v: object, with_time: bool = False) -> str:
    s = _text(v)
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return s
    return d.strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d")


def _numbered(title: str, i: int, count: int) -> str:
    return title if count <= 1 else f"{title} {i + 1}"


def _os(info: dict) -> list[Section]:
    t, o = i18n.t, info.get("os") or {}
    s = Section(t("ui.sys.section.os"))
    s.add(t("ui.sys.os_name"), _text(o.get("Caption")))
    s.add(t("ui.sys.os_version"), _text(o.get("DisplayVersion")) or _text(o.get("Version")))
    s.add(t("ui.sys.build"), _join(_text(o.get("BuildNumber")), _text(o.get("UBR")), sep="."))
    s.add(t("ui.sys.architecture"), _text(o.get("OSArchitecture")))
    s.add(t("ui.sys.installed"), _date(o.get("InstallDate"), with_time=True))
    s.add(t("ui.sys.last_boot"), _date(o.get("LastBootUpTime"), with_time=True))
    return [s]


def _computer(info: dict) -> list[Section]:
    t, c = i18n.t, info.get("computer") or {}
    s = Section(t("ui.sys.section.computer"))
    s.add(t("ui.sys.computer_name"), _text(c.get("Name")))
    s.add(t("ui.sys.manufacturer"), _text(c.get("Manufacturer")))
    s.add(t("ui.sys.model"), _text(c.get("Model")))
    s.add(t("ui.sys.system_type"), _text(c.get("SystemType")))
    return [s]


def _board(info: dict) -> list[Section]:
    t = i18n.t
    s = Section(t("ui.sys.section.board"))
    for b in as_list(info.get("board")):
        s.add(t("ui.sys.board"), _join(_text(b.get("Manufacturer")), _text(b.get("Product")), _text(b.get("Version")), sep=" "))
    for b in as_list(info.get("bios")):
        s.add(t("ui.sys.bios"), _join(_text(b.get("Manufacturer")), _text(b.get("SMBIOSBIOSVersion")), sep=" "))
        s.add(t("ui.sys.bios_date"), _date(b.get("ReleaseDate")))
    return [s]


def _cpu(info: dict) -> list[Section]:
    t = i18n.t
    cpus = as_list(info.get("cpu"))
    out = []
    for i, c in enumerate(cpus):
        s = Section(_numbered(t("ui.sys.section.cpu"), i, len(cpus)))
        s.add(t("ui.sys.model"), _text(c.get("Name")))
        cores, threads = _int(c.get("NumberOfCores")), _int(c.get("NumberOfLogicalProcessors"))
        if cores or threads:
            s.add(t("ui.sys.cores"), f"{cores or '?'} / {threads or '?'}")
        s.add(t("ui.sys.clock"), _mhz(c.get("MaxClockSpeed")))
        s.add(t("ui.sys.socket"), _text(c.get("SocketDesignation")))
        l2, l3 = (size((_int(c.get(k)) or 0) * 1024) for k in ("L2CacheSize", "L3CacheSize"))
        if l2 or l3:
            s.add(t("ui.sys.cache"), f"{l2 or '—'} / {l3 or '—'}")
        out.append(s)
    return out or [Section(t("ui.sys.section.cpu"))]


def _memory(info: dict) -> list[Section]:
    t = i18n.t
    o, c = info.get("os") or {}, info.get("computer") or {}
    modules = sorted(as_list(info.get("memory")), key=lambda m: (_text(m.get("DeviceLocator")), _text(m.get("BankLabel"))))
    s = Section(t("ui.sys.section.memory"))
    installed = sum(_int(m.get("Capacity")) or 0 for m in modules)
    s.add(t("ui.sys.mem_installed"), size(installed or c.get("TotalPhysicalMemory")))
    s.add(t("ui.sys.mem_visible"), size((_int(o.get("TotalVisibleMemorySize")) or 0) * 1024))
    s.add(t("ui.sys.mem_free"), size((_int(o.get("FreePhysicalMemory")) or 0) * 1024))
    for i, m in enumerate(modules):
        speed = _mhz(m.get("Speed"))
        configured = _int(m.get("ConfiguredClockSpeed"))
        if speed and configured and configured != _int(m.get("Speed")):
            speed += f" ({t('ui.sys.mem_configured', speed=_mhz(configured))})"
        label = _text(m.get("DeviceLocator")) or _text(m.get("BankLabel")) or f"#{i + 1}"
        s.add(label, _join(_join(_text(m.get("Manufacturer")), _text(m.get("PartNumber")), sep=" "),
                           size(m.get("Capacity")), SMBIOS_MEMORY_TYPES.get(_int(m.get("SMBIOSMemoryType")) or 0, ""), speed))
    return [s]


def _video(info: dict) -> list[Section]:
    t = i18n.t
    adapters = sorted(as_list(info.get("video")), key=lambda v: _text(v.get("Name")))
    dxgi = [d for d in as_list(info.get("dxgi")) if _text(d.get("description"))]
    used: set[int] = set()
    out = []
    for i, v in enumerate(adapters):
        name = _text(v.get("Name"))
        s = Section(_numbered(t("ui.sys.section.video"), i, len(adapters)))
        s.add(t("ui.sys.model"), name)
        # WMI AdapterRAM is a 32-bit value capped at 4 GB, so video memory comes from DXGI or is not shown
        for j, d in enumerate(dxgi):
            if j not in used and names_match(name, _text(d.get("description"))):
                used.add(j)
                s.add(t("ui.sys.video_memory"), size(d.get("dedicated_video_memory")))
                break
        driver_date = _date(v.get("DriverDate"))
        s.add(t("ui.sys.driver"), _join(_text(v.get("DriverVersion")), f"({driver_date})" if driver_date else "", sep=" "))
        w, h, hz = (_int(v.get(k)) for k in ("CurrentHorizontalResolution", "CurrentVerticalResolution", "CurrentRefreshRate"))
        if w and h:
            s.add(t("ui.sys.display_mode"), _join(f"{w} × {h}", f"{hz} {t('unit.hz')}" if hz else ""))
        out.append(s)
    return out or [Section(t("ui.sys.section.video"))]


def _storage(info: dict) -> list[Section]:
    t = i18n.t
    disks = Section(t("ui.sys.section.storage"))
    for d in sorted(as_list(info.get("disks")), key=lambda d: (_int(d.get("Index")) is None, _int(d.get("Index")) or 0)):
        removable = t("ui.sys.removable") if "removable" in _text(d.get("MediaType")).lower() else ""
        disks.add(t("ui.sys.disk", n=_text(d.get("Index")) or "?"),
                  _join(_text(d.get("Model")), size(d.get("Size"), decimal=True), _text(d.get("InterfaceType")), removable))
    volumes = Section(t("ui.sys.section.volumes"))
    for v in sorted(as_list(info.get("volumes")), key=lambda v: _text(v.get("DeviceID"))):
        total, free = size(v.get("Size")), size(v.get("FreeSpace"))
        volumes.add(_join(_text(v.get("DeviceID")), _text(v.get("VolumeName")), sep=" "),
                    _join(_text(v.get("FileSystem")), t("ui.sys.free_of", free=free, size=total) if total and free else total))
    return [disks, volumes]


def build_sections(info: dict) -> list[Section]:
    out: list[Section] = []
    for part in (_os, _computer, _board, _cpu, _memory, _video, _storage):
        out.extend(part(info or {}))
    return out


def _e(text: object) -> str:
    return escape(str(text), quote=True)


def sections_html(sections: list[Section]) -> str:
    """One table for all sections, so values line up in a single column."""
    out = ["<table cellspacing='4'>"]
    for s in sections:
        out.append(f"<tr><td colspan='2'><h3>{_e(s.title)}</h3></td></tr>")
        out += [f"<tr><td><b>{_e(k)}</b></td><td>{_e(v)}</td></tr>" for k, v in s.rows] \
            or [f"<tr><td colspan='2'>{_e(i18n.t('ui.sys.no_data'))}</td></tr>"]
    out.append("</table>")
    return "".join(out)


def sections_text(sections: list[Section]) -> str:
    lines = [f"{branding.APP_NAME} — {i18n.t('ui.tab.sysinfo')}"]
    for s in sections:
        lines += ["", f"[{s.title}]"]
        lines += [f"{k} {v}" if k.endswith(":") else f"{k}: {v}" for k, v in s.rows] or [i18n.t("ui.sys.no_data")]
    return "\n".join(lines) + "\n"

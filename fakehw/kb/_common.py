"""Helpers shared by the pci.ids / usb.ids parsers."""

import re
from dataclasses import dataclass, field
from typing import Iterator

_VERSION = re.compile(r"^#\s*Version:\s*(\S+)", re.M)
_DATE = re.compile(r"^#\s*Date:\s*(.+?)\s*$", re.M)

def decode_ids(data: bytes) -> str:
    """Upstream usb.ids contains a stray non-UTF-8 byte (in an unused HID table); replace instead of failing."""
    return data.decode("utf-8", errors="replace")


HEX2 = r"[0-9a-fA-F]{2}"
HEX4 = r"[0-9a-fA-F]{4}"


def parse_header(text: str) -> tuple[str | None, str | None]:
    """Version/date come from the leading comment block only."""
    head = []
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            head.append(line)
        else:
            break
    block = "\n".join(head)
    v, d = _VERSION.search(block), _DATE.search(block)
    return (v.group(1) if v else None, d.group(1) if d else None)


def iter_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield (indent_tabs, content) skipping blank and comment lines."""
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip("\t").startswith("#"):
            continue
        content = line.lstrip("\t")
        yield len(line) - len(content), content


@dataclass
class SubclassEntry:
    name: str
    prog_ifs: dict[int, str] = field(default_factory=dict)


@dataclass
class ClassEntry:
    name: str
    subclasses: dict[int, SubclassEntry] = field(default_factory=dict)


def class_lookup(
    classes: dict[int, ClassEntry], cls: int, sub: int | None = None, prog: int | None = None
) -> str | None:
    c = classes.get(cls)
    if c is None:
        return None
    if sub is None:
        return c.name
    s = c.subclasses.get(sub)
    if s is None:
        return None
    if prog is None:
        return s.name
    return s.prog_ifs.get(prog)

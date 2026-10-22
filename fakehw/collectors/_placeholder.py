"""Classification of serial / part-number strings that carry no real identity."""

import re

# Conventional "nothing here" strings seen in SMBIOS / firmware; compared case-insensitively.
PLACEHOLDER_TEXT = frozenset({
    "", "unknown", "none", "n/a", "na", "not specified", "not available", "to be filled by o.e.m.",
    "default string", "undefined", "serial number", "part number", "[empty]", "empty", "null", "-",
    "123456789", "1234567890", "0123456789",
})


def is_placeholder_text(value: str) -> bool:
    return value.strip().lower() in PLACEHOLDER_TEXT


def serial_shape(value: str) -> str:
    """normal | empty | zeros | ones | repeated | placeholder_text"""
    v = value.strip()
    if not v:
        return "empty"
    if re.fullmatch(r"0+", v):
        return "zeros"
    if re.fullmatch(r"[Ff]+", v):
        return "ones"
    if len(v) >= 4 and len(set(v)) == 1:
        return "repeated"
    if is_placeholder_text(v):
        return "placeholder_text"
    return "normal"


def normalise(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def names_match(a: str, b: str) -> bool:
    """Loose model-name comparison: equal after normalisation, or one contains the other (truncated names)."""
    na, nb = normalise(a), normalise(b)
    return bool(na and nb and (na == nb or na in nb or nb in na))

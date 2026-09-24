import ipaddress
import re

MAC_REGEX = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")


def validate_ip(ip_str: str | None) -> bool:
    if not ip_str or not ip_str.strip():
        return True
    try:
        ipaddress.ip_address(ip_str.strip())
        return True
    except ValueError:
        return False


def validate_mac(mac_str: str | None) -> bool:
    if not mac_str or not mac_str.strip():
        return True
    return bool(MAC_REGEX.match(mac_str.strip()))


from enum import Enum
from typing import Any, TypeVar

from fastapi import HTTPException, status

E = TypeVar("E", bound=Enum)

NONE_STRINGS = {"", "none", "null", "undefined", "all", "*"}


def parse_optional_int(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    s = str(val).strip().lower()
    if not s or s in NONE_STRINGS:
        return None
    try:
        return int(s)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Input should be a valid integer, unable to parse '{val}' as an integer",
        )


def parse_optional_str(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in NONE_STRINGS:
        return None
    return s


def parse_optional_enum(val: Any, enum_cls: type[E]) -> E | None:
    if isinstance(val, enum_cls):
        return val
    s = parse_optional_str(val)
    if not s:
        return None
    for item in enum_cls:
        if item.value.lower() == s.lower() or item.name.lower() == s.lower():
            return item
    valid_vals = [e.value for e in enum_cls]
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Invalid value '{val}'. Allowed values: {valid_vals}",
    )

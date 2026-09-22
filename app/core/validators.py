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

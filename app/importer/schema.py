"""Single source of truth for computer fleet import schema."""

from typing import Any, NamedTuple


class ColumnSpec(NamedTuple):
    key: str
    header_en: str
    header_ru: str
    aliases: list[str]
    field_name: str
    type_name: str
    required: bool
    default: Any
    example_value: str
    description_ru: str
    description_en: str


FLEET_IMPORT_COLUMNS: list[ColumnSpec] = [
    ColumnSpec(
        key="hostname",
        header_en="hostname",
        header_ru="имя_хоста",
        aliases=["hostname", "компьютер", "имя хоста", "имя_хоста", "компьютер/hostname"],
        field_name="hostname",
        type_name="string",
        required=True,
        default=None,
        example_value="PC-OFFICE-101",
        description_ru="Уникальное сетевое имя компьютера (обязательно)",
        description_en="Unique network hostname of the computer (required)",
    ),
    ColumnSpec(
        key="ip",
        header_en="ip",
        header_ru="ip_адрес",
        aliases=["ip", "ip-адрес", "ip_адрес", "ip address"],
        field_name="ip",
        type_name="ip",
        required=False,
        default=None,
        example_value="192.168.1.50",
        description_ru="IPv4 или IPv6 адрес устройства",
        description_en="IPv4 or IPv6 address of the device",
    ),
    ColumnSpec(
        key="mac",
        header_en="mac",
        header_ru="mac_адрес",
        aliases=["mac", "mac-адрес", "mac_адрес", "mac address"],
        field_name="mac",
        type_name="mac",
        required=False,
        default=None,
        example_value="00:11:22:33:44:55",
        description_ru="MAC-адрес сетевого интерфейса",
        description_en="Network interface MAC address",
    ),
    ColumnSpec(
        key="os",
        header_en="os",
        header_ru="ос",
        aliases=["os", "операционная система", "ос", "operating system"],
        field_name="os",
        type_name="string",
        required=False,
        default=None,
        example_value="Windows 11 Pro",
        description_ru="Название операционной системы",
        description_en="Operating system name",
    ),
    ColumnSpec(
        key="location",
        header_en="location",
        header_ru="расположение",
        aliases=["location", "кабинет", "расположение", "комната", "room"],
        field_name="location",
        type_name="string",
        required=False,
        default=None,
        example_value="Room 302",
        description_ru="Кабинет или физическое местоположение",
        description_en="Office or physical room location",
    ),
    ColumnSpec(
        key="owner",
        header_en="owner",
        header_ru="владелец",
        aliases=["owner", "владелец", "пользователь", "user", "owner_username"],
        field_name="owner",
        type_name="user",
        required=False,
        default=None,
        example_value="admin",
        description_ru="Логин или email закрепленного пользователя",
        description_en="Username or email of the assigned owner user",
    ),
    ColumnSpec(
        key="is_round_the_clock",
        header_en="is_round_the_clock",
        header_ru="круглосуточный_24_7",
        aliases=[
            "is_round_the_clock",
            "24/7",
            "круглосуточный",
            "круглосуточный_24_7",
            "is_rtc",
            "rtc",
        ],
        field_name="is_round_the_clock",
        type_name="boolean",
        required=False,
        default=False,
        example_value="нет",
        description_ru="Работает 24/7 (да/нет, true/false, 1/0)",
        description_en="Runs 24/7 (yes/no, true/false, 1/0)",
    ),
    ColumnSpec(
        key="notes",
        header_en="notes",
        header_ru="примечания",
        aliases=["notes", "заметки", "примечания", "комментарий", "comments"],
        field_name="notes",
        type_name="string",
        required=False,
        default=None,
        example_value="Основное рабочее место",
        description_ru="Дополнительные заметки и комментарии",
        description_en="Additional notes and comments",
    ),
]


def resolve_column_value(row_dict: dict[str, Any], col_spec: ColumnSpec) -> str:
    """Find value for col_spec from row dict by checking all aliases."""
    for alias in col_spec.aliases:
        alias_clean = alias.strip().lower()
        if alias_clean in row_dict:
            val = str(row_dict[alias_clean]).strip()
            if val:
                return val
    return ""


def parse_boolean_value(val_str: str) -> bool:
    """Parse boolean value from common representations."""
    cleaned = val_str.strip().lower()
    return cleaned in ("1", "true", "да", "yes", "y", "+", "rtc")

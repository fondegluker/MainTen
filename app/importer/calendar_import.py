"""Single source of truth schema and template generator for bulk calendar imports (Issue 2)."""

import json
from typing import Any

CALENDAR_IMPORT_FIELDS = [
    {
        "name": "date",
        "type": "string (ISO YYYY-MM-DD)",
        "required": True,
        "description_ru": "Дата в формате ГГГГ-ММ-ДД (например, 2025-05-09)",
        "description_en": "Date in YYYY-MM-DD format (e.g. 2025-05-09)",
    },
    {
        "name": "kind",
        "type": "string (workday | weekend | holiday | short_day)",
        "required": True,
        "description_ru": "Тип дня: workday, weekend, holiday, short_day",
        "description_en": "Day kind: workday, weekend, holiday, short_day",
    },
    {
        "name": "is_working",
        "type": "boolean (true | false | 1 | 0)",
        "required": False,
        "description_ru": "Флаг рабочего дня (по умолчанию определяется по kind)",
        "description_en": "Working day flag (defaults based on day kind)",
    },
    {
        "name": "description",
        "type": "string",
        "required": False,
        "description_ru": "Описание или название праздника/события",
        "description_en": "Description or holiday title",
    },
]

CALENDAR_TEMPLATE_ENTRIES: list[dict[str, Any]] = [
    {
        "date": "2025-05-01",
        "kind": "holiday",
        "is_working": False,
        "description": "Праздник труда / Labor Day",
    },
    {
        "date": "2025-05-02",
        "kind": "workday",
        "is_working": True,
        "description": "Рабочий день / Workday",
    },
    {
        "date": "2025-05-03",
        "kind": "weekend",
        "is_working": False,
        "description": "Выходной суббота / Saturday weekend",
    },
    {
        "date": "2025-05-08",
        "kind": "short_day",
        "is_working": True,
        "description": "Предпраздничный сокращенный день / Short workday",
    },
]


def generate_calendar_template_csv() -> str:
    """Generate canonical CSV template for calendar import."""
    headers = ["date", "kind", "is_working", "description"]
    rows = [",".join(headers)]
    for entry in CALENDAR_TEMPLATE_ENTRIES:
        desc = entry["description"].replace('"', '""')
        desc_quoted = f'"{desc}"' if "," in desc or " " in desc else desc
        row_str = f"{entry['date']},{entry['kind']},{str(entry['is_working']).lower()},{desc_quoted}"
        rows.append(row_str)
    return "\n".join(rows) + "\n"


def generate_calendar_template_json() -> str:
    """Generate canonical JSON template for calendar import."""
    return json.dumps(CALENDAR_TEMPLATE_ENTRIES, indent=2, ensure_ascii=False) + "\n"

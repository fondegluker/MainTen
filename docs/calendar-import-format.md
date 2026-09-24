# Calendar Import Format Specification (CSV / JSON)

This document describes the specification, column schema, allowed values, validation rules, and template download options for bulk importing calendar records into the Computer Fleet Maintenance Scheduler (CFMS).

---

## 1. File Formats & Encoding

- **Accepted Extensions:** `.csv` and `.json`
- **Encoding:** `UTF-8` (without BOM or with standard UTF-8 BOM)

---

## 2. CSV Schema & Specification

### Header Row
The CSV header row is **required** and must contain the following column names (case-insensitive):
```csv
date,kind,is_working,description
```

### Columns Contract

| Column Name | Type | Required | Allowed Values / Format | Description |
| :--- | :--- | :--- | :--- | :--- |
| `date` | String | **Yes** | ISO `YYYY-MM-DD` (e.g. `2025-05-09`) | Specific calendar date |
| `kind` | String | **Yes** | `workday`, `weekend`, `holiday`, `short_day` | Day classification type |
| `is_working` | Boolean | No | `true`, `false`, `1`, `0`, `да`, `yes` | Working day status flag. If omitted, defaults based on `kind` (`workday` and `short_day` = `true`; `weekend` and `holiday` = `false`). |
| `description` | String | No | Free form text | Localized event title or holiday description |

### Example CSV Rows (One per Day Kind)
```csv
date,kind,is_working,description
2025-05-01,holiday,false,"Праздник труда"
2025-05-02,workday,true,"Рабочий день"
2025-05-03,weekend,false,"Суббота (выходной)"
2025-05-08,short_day,true,"Предпраздничный сокращенный день"
```

### Duplicate Handling
If an imported file contains a `date` that already exists in the `working_calendar` table, the existing record is **updated** with the new `kind`, `is_working`, `description`, and `source = 'admin'`.

---

## 3. JSON Schema & Specification

JSON files must contain a **top-level array of objects**.

### Field Specifications

- `date` (string, required): `YYYY-MM-DD`
- `kind` (string, required): `"workday"`, `"weekend"`, `"holiday"`, or `"short_day"`
- `is_working` (boolean, optional): `true` or `false`
- `description` (string, optional): Notes or holiday title

### Example JSON Array
```json
[
  {
    "date": "2025-05-01",
    "kind": "holiday",
    "is_working": false,
    "description": "Праздник труда / Labor Day"
  },
  {
    "date": "2025-05-02",
    "kind": "workday",
    "is_working": true,
    "description": "Рабочий день / Workday"
  },
  {
    "date": "2025-05-03",
    "kind": "weekend",
    "is_working": false,
    "description": "Выходной суббота / Saturday weekend"
  },
  {
    "date": "2025-05-08",
    "kind": "short_day",
    "is_working": true,
    "description": "Предпраздничный сокращенный день / Short workday"
  }
]
```

---

## 4. Validation & Error Handling

- **Invalid Date Format:** Dates not matching `YYYY-MM-DD` ISO format trigger a line/record error.
- **Corrupted Structure:** Non-array JSON or unparseable CSV files cause the entire upload to be rejected with an error message.
- **Atomic Database Commit:** All valid records are committed in a nested transaction. If an unrecoverable database exception occurs, the transaction rolls back.

---

## 5. Downloadable Template Routes

The application serves canonical templates generated directly from the importer schema constant:

- **CSV Template:** `GET /admin/calendar/import/template.csv`
- **JSON Template:** `GET /admin/calendar/import/template.json`

*(Requires `ADMIN` role authentication)*

---

## 6. Administrator Workflow

1. Navigate to `/admin/calendar` and click **"Импорт CSV/JSON"**.
2. Download a starting template (**"Скачать шаблон CSV"** or **"Скачать шаблон JSON"**).
3. Edit the file using any text editor or spreadsheet program, ensuring `UTF-8` encoding.
4. Select the modified file in the modal form and click **"Загрузить"**.
5. The 7-column calendar grid will immediately display the updated days.

---

## 7. Calendar Export

- **Current Status:** Direct calendar export to CSV/JSON via UI is **not implemented** in v1. Maintainers may perform database backups via `pg_dump` or query `working_calendar`.

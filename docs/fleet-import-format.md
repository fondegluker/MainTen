# Fleet Import Specification & Template Format

## 1. Canonical Template File & Download Route
- **Canonical Repository Path:** `app/importer/assets/fleet_import_template.xlsx`
- **Download Route:** `GET /admin/import/template` (ADMIN role required)
- **Saved Filename:** `fleet_import_template.xlsx`
- **One-line Admin Instruction:** "Download the template from `/admin/import`, fill it, upload it back."

---

## 2. Spreadsheet Structure

The workbook contains two sheets:

### Sheet 1: `Computers`
Contains the data rows to be parsed and imported into the `computers` table.
- **Row 1:** Headers matching the specification below. The header row is frozen.
- **Row 2+:** Data rows.

### Sheet 2: `Readme`
Contains field legends and description notes side-by-side in Russian and English.

---

## 3. Column Specification

| Header (EN) | Header (RU) | Target DB Field | Data Type | Required | Default | Validation & Format | Example |
|---|---|---|---|---|---|---|---|
| `hostname` | `имя_хоста` | `Computer.hostname` | String | **Yes** | None | Must be non-empty and unique within file and database. | `PC-OFFICE-101` |
| `ip` | `ip_адрес` | `Computer.ip` | IP Address | No | None | Valid IPv4 or IPv6 format if provided. | `192.168.1.50` |
| `mac` | `mac_адрес` | `Computer.mac` | MAC Address | No | None | Valid MAC format (`XX:XX:XX:XX:XX:XX` or `XX-XX-XX-XX-XX-XX`) if provided. | `00:11:22:33:44:55` |
| `os` | `os` | `Computer.os` | String | No | None | Freeform string (e.g., Windows 11 Pro, Ubuntu 22.04). | `Windows 11 Pro` |
| `location` | `расположение` | `Computer.location` | String | No | None | Office number or room description. | `Room 302` |
| `owner` | `владелец` | `Computer.owner_user_id` | User Lookup | No | None | Looks up existing user by `username` or `email_or_login`. If not found, a warning is raised and owner remains unassigned. | `admin` |
| `is_round_the_clock` | `круглосуточный_24_7` | `Computer.is_round_the_clock` | Boolean | No | `False` | Accepts boolean values: `1`, `true`, `да`, `yes`, `y`, `+`, `rtc`. All other values evaluate to `False`. | `нет` |
| `notes` | `примечания` | `Computer.notes` | String | No | None | Additional notes or comments. | `Основное рабочее место` |

---

## 4. Parser Behavior Rules

1. **Sheet Name:** The importer reads from sheet `Computers` if present, otherwise from the first active sheet.
2. **Header Row:** Row 1 is expected to contain the header titles. The importer checks column aliases defined in `app/importer/schema.py::FLEET_IMPORT_COLUMNS`.
3. **Unknown Columns:** Extra or unknown columns are ignored safely.
4. **Duplicates:** Duplicate `hostname` entries within the uploaded Excel file trigger a critical error.
5. **Existing Computers:** If `hostname` already exists in the database, the diff type is classified as `Update`. Existing non-null computer fields are updated with new values upon import confirmation.
6. **Partial Failures & Error Enforcement:** If ANY row contains validation errors (e.g. invalid IP/MAC format or missing hostname), the entire file import is blocked until errors are resolved.
7. **Audit Log:** Successful imports log an `excel_import_fleet` entry to the `audit_log` table with summary metadata (total processed, created count, updated count, original filename).

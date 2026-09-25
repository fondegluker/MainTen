# Architectural Decisions & Design Rationale

## Working Branch Model & Repository Strategy

- **Working Branch Model:** Development occurs in a single long-lived working branch (auto-generated `jules-*` branch name).
- **Maintainer Archival Snapshots:** Human maintainers periodically snapshot verified iteration baselines into archival branches (`iteration-1`, `iteration-2`, `iteration-3`) for release bookkeeping. Automated agents (Jules) never create, rename, or delete branches on remote.
- **Rule for Jules:** "Work ONLY in the current branch. Do not create, rename, or delete branches. Do not push to main. Push commits to the branch you were started on."
- **Minimal `main` Branch:** `main` is intentionally kept minimal and untouched.

## Package Naming & CI Quality Rules

- **Python package naming rule:** Never use Python reserved keywords (such as `import`, `class`, `def`, `pass`) as package or module names under `app/`. The fleet import package is canonically named `app.importer`.
- **Required CI checks:**
  1. `import-smoke` (`pytest tests/test_import_smoke.py -x -q`): Recursively imports all modules under `app/`, checks that no module/package uses Python keywords, and asserts `app.importer` package structure and schema constant sharing.
  2. `lint` (`ruff check .`): Linter check.
  3. `format` (`ruff format --check .`): Formatting check.
  4. `tests` (`pytest`): Full test suite execution with `--import-mode=importlib`.
  5. `e2e-smoke` (`pytest tests/e2e/ -x -q`): Mandatory end-to-end browser smoke suite using Playwright walking every role through every navigation link, asserting HTTP status codes (200 for allowed, 403 for forbidden), toggling localization, and testing magic link booking.

## Combined Hotfix Resolutions (Issues 1–5)

- **Issue 1 (Systemic Optional Query Parameter Parsing)**: Created reusable parsing helpers (`parse_optional_int`, `parse_optional_str`, `parse_optional_enum` in `app/core/validators.py`) that map empty strings `""`, whitespace, `"null"`, `"undefined"`, `"none"`, `"all"`, and `"*"` to `None`. Applied across all list endpoints so `GET /admin/computers?owner_id=` returns HTTP 200 with all rows instead of throwing HTTP 422 int parsing errors.
- **Issue 2 (Centered Selection Window & Single Source of Truth Calendar Filtering)**:
  - Calculated selection window as centered around the trigger/due date (`[trigger_date - selection_window_days//2 .. trigger_date + selection_window_days//2]`).
  - Implemented `is_working_day(cal_date, db) -> bool` in `app/services/scheduling_service.py` as the single source of truth for working day checks across the application.
  - Disabled non-working days, past dates, technician-booked dates, and computer-booked dates in the UI with explicit explanation badges instead of silently hiding them.
  - Added automatic escalation audit logging (`escalate_empty_window`) when zero selectable dates exist in an active selection window.
- **Issue 3 (Admin Settings Page & Persistence)**: Created `/admin/settings` (ADMIN only) with form validations (`intervals > 0`, `window > 0`, `0 <= prompt_start_offset <= selection_window_days`), audit logging (`update_settings`), single-row `app_settings` persistence in the `settings` table, and a reset button (`POST /admin/settings/reset`).
- **Issue 4 (Protocol Editor & Reference Protection)**: Created `/admin/protocol` (ADMIN only) with RU/EN mandatory title inputs, dense reordering (`order_index`), and deletion protection for protocol items referenced in `maintenance_event_checks` (recommending deactivation `is_active = False`).
- **Issue 5 (Working Calendar Editor & Migration)**: Created `/admin/calendar` (ADMIN only) with month view navigation, single-day toggles, `holiday` and `short_day` markings, bulk CSV/JSON import, and reset to Belarus calendar seed defaults. Added migration `88b9c0d1e2f3` for `DayKind.SHORT_DAY` and `WorkingCalendar.source = 'admin'`.

## Permanent E2E Smoke Test Suite Adoption

- **Mandatory Requirement**: Adopted `e2e-smoke` as a permanent, non-negotiable requirement for every present and future iteration.
- **Chosen Browser Driver**: Playwright (Python `playwright` sync API) was selected for native headless Chromium execution, multi-context session isolation per role, fast selector execution, and robust NetworkIdle waiting.
- **Seeding Strategy**: Implemented `app/seed_e2e.py` providing an idempotent seed dataset (1 admin, 1 technician, 1 observer, 1 user, 2 computers, 1 protocol item, and 2025–2026 working calendar). Accessible via CLI (`python -m app.seed_e2e`) and `POST /admin/seed-e2e`.
- **Log Inspection**: Automated assertion in `tests/e2e/test_smoke.py` scanning application container logs for unhandled exceptions or tracebacks.

## Fleet Import Template & Single Source of Truth

- Chosen `app.importer` as the canonical Python package name (resolving reserved keyword conflict with `import`).
- Created `app/importer/schema.py` containing `FLEET_IMPORT_COLUMNS` schema constant as the single source of truth for column titles, database field mappings, data types, required flags, default values, example values, and localized descriptions.
- Created `app/importer/template.py` exposing `build_template() -> bytes` and `TEMPLATE_FILENAME = "fleet_import_template.xlsx"`.
- Generated and committed canonical asset at `app/importer/assets/fleet_import_template.xlsx`.
- Both the Excel importer parser (`app/routers/import_fleet.py`) and the template generator (`app/importer/template.py`) import `FLEET_IMPORT_COLUMNS` to ensure the template and parser can never diverge.
- Served route `GET /admin/import/template` dynamically regenerates template bytes on-the-fly and returns HTTP 200 with `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` and `Content-Disposition: attachment; filename="fleet_import_template.xlsx"`.
- Documented full specification in `docs/fleet-import-format.md` and updated `README.md`.

## Dashboard 500 Hotfix & Postgres Enum Alignment

- Resolved HTTP 500 `DataError` on `/admin/dashboard` in PostgreSQL environments caused by uppercase enum type definition (`PLANNED`, `IN_PROGRESS`, `DONE`, `MISSED`, `CANCELLED`) in initial migration versus lowercase string values (`planned`, `in_progress`, `done`, `missed`, `cancelled`) in Python ORM model.
- Added Alembic migration `77a8b9c0d1e2_fix_enum_values.py` converting PostgreSQL `maintenanceeventstatus` enum values to match SQLAlchemy ORM string values.
- Updated `app/main.py` exception handler to issue HTTP 302 redirects to `/auth/login` for unauthenticated HTML requests.
- Added E2E Docker Compose smoke test in `.github/workflows/ci.yml` verifying live container startup, login, and `/admin/dashboard` 200 response on every push.

## Reconciliation & Requirement Verification (Step 0 Audit)

An audit was conducted against `docs/requirements.md` §1–§3 and §9 Iteration 1 to ensure full compliance before beginning Iteration 2:

- **`working_calendar` table**: Verified model in `app/models/models.py`, repository in `app/repositories/calendar_repository.py`, and Alembic migration `52f9a72b834e` seeding 2025–2026 Belarus working days (Mon–Fri), weekends, and public holidays (`holiday` kind) with unique index on `date`.
- **Docker dependencies**: Verified `Dockerfile` installs system tools `nmap` and `arp-scan`.
- **`AuthProvider` abstraction**: Verified `BaseAuthProvider` in `app/auth/base.py`, `LocalAuthProvider` with Argon2/Bcrypt in `app/auth/providers.py` (with case-insensitive & whitespace-trimmed matching), and `AdAuthProvider` stub.
- **i18n**: Verified translation module `app/core/i18n.py` with Russian default and English support, including UI language switcher `/set-locale`.
- **Auth flows**: Verified local username/password login for ADMIN/TECHNICIAN and signed magic-link authentication for USERS.
- **CI Pipeline**: Verified `.github/workflows/ci.yml` runs linting (`ruff`) and automated tests (`pytest`) against PostgreSQL.

No gaps were identified in Step 0 audit.

## Default Admin User Credentials

- Seeded default administrator account via Alembic migration (`63a1b2c4d5e6`):
  - **Username**: `admin`
  - **Email/Login**: `admin@cfms.local`
  - **Default Password**: `admin123`
  - **Role**: `ADMIN`
- Password is stored hashed using `argon2` via `LocalAuthProvider`.

## Helper Scripts Integration

The repository integrates shell scripts for deployment and local testing:
- `run.sh`: Clones/updates repository, builds Docker containers, and runs web service on port 8000.
- `stop.sh`: Stops running containers while preserving PostgreSQL data volumes.
- `install_docker.sh`: Installs Docker Engine and Docker Compose v2 on Ubuntu.

## Iteration 2 Architecture & Design Decisions

### Admin CRUD & Audit Logging
- **Service**: Implemented `app/services/audit_service.py` with `log_audit()` to consistently log every mutating operation (create, update, deactivate, reset_password, reissue_magic_link, delete, and import) into the `audit_log` table with `before_json` and `after_json` snapshots.
- **Admin Routers & Views**:
  - `/admin/users`: Management of system accounts (ADMIN, TECHNICIAN, USER, OBSERVER) with creation, edit, password hashing/reset, magic-link reissue, soft-deactivation, pagination, sorting, and multi-field search.
  - `/admin/computers`: Fleet device management with hostname, IP, MAC, OS, location, user owner association ("Manager" virtual property support), 24/7 (RTC) flags, pagination, sorting, and IP/MAC format validations.
  - `/admin/technicians`: Specialized view filtering users by `TECHNICIAN` role with daily maintenance capacity configuration (default 1).

### Magic Link Token Invalidation & Security Status Code
- **Token Invalidation**: Magic link tokens embed a `version` field. Re-issuing a magic link increments `magic_token_version_{user_id}` in the `settings` table, rendering all previously issued tokens invalid.
- **HTTP Status Code**: Verification of expired or invalidated magic-link tokens returns HTTP `401 Unauthorized` with clear error messaging.

### Excel Fleet Import with Preview, Diffs & Hard Error Enforcement
- **Documentation Route (Option B)**: The fleet import documentation link is served dynamically via `GET /admin/docs/fleet-import-format` (and top-level `/docs/fleet-import-format.md`) requiring ADMIN authentication. The endpoint renders `FLEET_IMPORT_COLUMNS` schema details with HTTP 200.
- **Library**: `openpyxl` is used for parsing `.xlsx` spreadsheets and generating the downloadable template (`/admin/import/template`).
- **Staging, Diffing & Validation**:
  - `POST /admin/import/preview`: Parses uploaded `.xlsx` file, normalizes header columns (supporting both EN and RU headers), resolves user owner IDs, validates missing mandatory fields, checks IP/MAC regex formats, detects duplicates within the file, and classifies row diffs (`new`, `update`, `conflict`).
  - Staged valid rows are held in an in-memory session cache (`IMPORT_STAGING_CACHE`) keyed by a UUID token.
  - Hard errors block confirmation until resolved.
  - `POST /admin/import/confirm`: Commits valid previewed rows to the `computers` table in a single atomic database transaction (`db.begin_nested()`) and records an `excel_import_fleet` entry with raw filename and report details in `audit_log`.

## UI & Documentation Hotfix Resolutions (Issues 1–5)

- **Issue 1 (Monday-First 7-Column Calendar Grid Layout)**:
  - Created `get_month_calendar_grid()` in `app/services/scheduling_service.py` computing Monday-first 7-column grid structures for any month/year in `[current_year .. current_year + 10]`.
  - Updated `/admin/calendar` template and router to display 7 weekday headers (`Пн`..`Вс` / `Mon`..`Sun`), leading/trailing blank cells, 10-year year navigation, and accessible high-contrast indicators for working days, weekends, holidays, short days, and today.
- **Issue 2 (Bulk Calendar Import Documentation & Template Routes)**:
  - Created `app/importer/calendar_import.py` as single source of truth schema and template generator for bulk calendar imports.
  - Added template download routes `GET /admin/calendar/import/template.csv` and `GET /admin/calendar/import/template.json` (ADMIN restricted).
  - Documented full CSV/JSON schemas, allowed values, validation rules, step-by-step instructions, and export notes in `docs/calendar-import-format.md`, and linked from `README.md` and `/admin/calendar` modal UI.
- **Issue 3 (Localized Date Picker Weekday & Month Names)**:
  - Created `format_date_localized()` in `app/core/i18n.py` formatting dates with localized weekday abbreviations (`Пн`..`Вс` in `ru` vs `Mon`..`Sun` in `en`).
  - Updated `get_window_calendar_days` and `user.py` router to format dates according to the user's active locale.
- **Issue 4 (Prohibit Weekend Selection, Single Source of Truth & Shared Date Picker Component)**:
  - **Duplication Audit & Finding:** Investigated `/user/my-computers` in `app/templates/user_computers.html`. Block A (`window_state == 'active'`) checked `dt.is_selectable` to disable invalid days, whereas Block B (`planned_event` reschedule block) rendered `item.available_dates` without `is_selectable` checks, allowing non-working dates to be selected in the UI.
  - **Single Source of Truth Service Function:** Created `compute_available_dates()` in `app/services/scheduling_service.py` returning `window_start`, `window_end`, `prompt_start`, ISO `selectable` dates list, `blocked` dates list with exact reason codes (`weekend`, `holiday`, `booked`, `past`, `capacity_full`), and formatted day objects.
  - **API Endpoint:** Exposed `GET /api/computers/{id}/available-dates` in `app/routers/user.py` returning JSON date availability metadata.
  - **3+3 Grid Layout Choice & Sunday Exclusion:** Configured date picker grid to render 2 rows × 3 columns (`WEEK_LAYOUT = [["mon", "tue", "wed"], ["thu", "fri", "sat"]]` defined in `app/core/i18n.py`). Sunday is never a maintenance date and is excluded completely from cells, headers, and DOM outputs without using CSS `display:none`. Saturday is rendered as clickable if selectable, or disabled if non-working/blocked.
  - **Shared Client Component & Code Removal:** Created reusable Jinja component `app/templates/components/date_picker.html` exposing `render_date_picker()`. Removed the duplicate picker loop in `user_computers.html` Block B entirely, rendering both Block A and Block B through `render_date_picker()`.
  - **UX & Defense-in-Depth Validation:** Enforced `disabled`, `aria-disabled="true"`, greyed styles, and tooltip hover titles (`"Выходной"`, `"Праздник"`, `"Уже занято"`, `"Прошедшая дата"`, `"Вне окна выбора"`) on non-selectable days across all pickers. Added JS submit handler to display server 422 responses as inline localized error alerts instead of raw JSON. Updated `validate_maintenance_date()` to validate against `compute_available_dates()`.
- **Issue 5 (Left Sidebar Navigation Layout)**:
  - Refactored `app/templates/base.html` replacing horizontal top navigation with a fixed left sidebar (`aside#sidebar-nav`).
  - Implemented default collapsed state (`w-16`), desktop hover expansion (`w-64`), 375px mobile viewport drawer overlay with hamburger toggle, and keyboard accessibility (Escape key handler, focus rings, `aria-expanded`, `aria-label`).

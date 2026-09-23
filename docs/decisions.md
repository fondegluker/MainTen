# Architectural Decisions & Design Rationale

## Fleet Import Template & Single Source of Truth

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

### Excel Fleet Import with Preview, Diffs & Hard Error Enforcement
- **Library**: `openpyxl` is used for parsing `.xlsx` spreadsheets and generating the downloadable template (`/admin/import/template`).
- **Staging, Diffing & Validation**:
  - `POST /admin/import/preview`: Parses uploaded `.xlsx` file, normalizes header columns (supporting both EN and RU headers), resolves user owner IDs, validates missing mandatory fields, checks IP/MAC regex formats, detects duplicates within the file, and classifies row diffs (`new`, `update`, `conflict`).
  - Staged valid rows are held in an in-memory session cache (`IMPORT_STAGING_CACHE`) keyed by a UUID token.
  - Hard errors block confirmation until resolved.
  - `POST /admin/import/confirm`: Commits valid previewed rows to the `computers` table in a single atomic database transaction (`db.begin_nested()`) and records an `excel_import_fleet` entry with raw filename and report details in `audit_log`.

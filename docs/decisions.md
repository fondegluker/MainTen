# Architectural Decisions & Design Rationale

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

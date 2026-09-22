# Architectural Decisions & Design Rationale

## Reconciliation & Requirement Verification (Step 0 Audit)

An audit was conducted against `docs/requirements.md` §1–§3 and §9 Iteration 1 to ensure full compliance before beginning Iteration 2:

- **`working_calendar` table**: Verified model in `app/models/models.py`, repository in `app/repositories/calendar_repository.py`, and Alembic migration `52f9a72b834e` seeding 2025–2026 Belarus working days (Mon–Fri), weekends, and public holidays (`holiday` kind) with unique index on `date`.
- **Docker dependencies**: Verified `Dockerfile` installs system tools `nmap` and `arp-scan`.
- **`AuthProvider` abstraction**: Verified `BaseAuthProvider` in `app/auth/base.py`, `LocalAuthProvider` with Argon2/Bcrypt in `app/auth/providers.py`, and `AdAuthProvider` stub.
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

## Iteration 2 Architecture & Design Decisions

### Admin CRUD & Audit Logging
- **Service**: Implemented `app/services/audit_service.py` with `log_audit()` to consistently log every mutating operation (create, update, toggle active, delete, and import) into the `audit_log` table with `before_json` and `after_json` snapshots.
- **Admin Routers & Views**:
  - `/admin/users`: Management of system accounts (ADMIN, TECHNICIAN, USER, OBSERVER) with creation, edit, password hashing, and active/inactive status toggling.
  - `/admin/computers`: Fleet device management with hostname, IP, MAC, OS, location, user owner association, and 24/7 (RTC) flags.
  - `/admin/technicians`: Specialized view filtering users by `TECHNICIAN` role for schedule monitoring.

### Excel Fleet Import with Preview & Validation
- **Library**: `openpyxl` was selected for parsing `.xlsx` spreadsheets.
- **Staging & Validation**:
  - `POST /admin/import/preview`: Parses uploaded `.xlsx` file, normalizes header columns (supporting both EN and RU headers like `hostname`/`компьютер`, `owner`/`владелец`, `is_round_the_clock`/`24/7`), resolves user owner IDs, validates missing mandatory fields, checks for duplicate hostnames, and displays a preview table highlighting errors or warnings.
  - Staged valid rows are held in an in-memory session cache (`IMPORT_STAGING_CACHE`) keyed by a UUID token.
  - `POST /admin/import/confirm`: Commits valid previewed rows to the `computers` table (creating new records or updating existing ones) and records an `excel_import_fleet` entry in `audit_log`.

## Working Calendar Delta & Belarus Holidays

- Added `working_calendar` table via Alembic migration (`52f9a72b834e`).
- Automatically seeds default working days (Mon-Fri) and official Belarusian public holidays (`holiday` kind) for current and next calendar years (2025-2026).
- Unique index on `date` guarantees no duplicate entries.
- `CalendarRepository` provides helper queries for checking working days and retrieving working day ranges.

## System Packages & Dependencies

- Docker container includes system network utilities `nmap` and `arp-scan` to support network scanning functionality (§1 & §5.1).

## Auth Architecture Abstraction

An explicit abstraction was implemented to isolate authentication strategy:

```
                  +-------------------------+
                  |    BaseAuthProvider     |
                  +-------------------------+
                               |
            +------------------+------------------+
            |                                     |
+-----------------------+             +-----------------------+
|   LocalAuthProvider   |             |    AdAuthProvider     |
|   (Argon2 / Bcrypt)   |             |   (Stub / Interface)  |
+-----------------------+             +-----------------------+
```

1. **LocalAuthProvider**: Handles local database credential checks using Argon2 password hashing.
2. **AdAuthProvider**: Stub class defining standard `authenticate` and `get_user` interface so Active Directory/LDAP backend can be easily swapped in future iterations without altering core routing logic.
3. **Magic Links**: End-users tied to computers authenticate via signed HMAC tokens containing `user_id` and optional `computer_id`, issuing secure HTTP-only session cookies upon click.

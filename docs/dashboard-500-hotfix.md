# Dashboard HTTP 500 Hotfix Diagnosis & Audit Report

## 1. Summary of Reproduced Issues & Root Causes

During runtime reproduction against Iteration 2 requirements (§5.1, §9):

1. **Issue 1 — Enum Value Mismatch in Postgres Migration Schema**:
   - **URL**: `http://localhost:8000/admin/dashboard` & `GET /`
   - **Role**: `ADMIN`
   - **HTTP Method**: `GET`
   - **Exact Traceback**:
     ```
     sqlalchemy.exc.DataError: (psycopg2.errors.InvalidTextRepresentation) invalid input value for enum maintenanceeventstatus: "planned"
     LINE 1: ...WHERE maintenance_events.status = 'planned'
     ```
   - **Root Cause**: In the initial Alembic migration `4573d757029f_initial_schema.py`, the `maintenanceeventstatus` Postgres ENUM type was created using uppercase enum names (`PLANNED`, `IN_PROGRESS`, `DONE`, `MISSED`, `CANCELLED`), whereas the Python `MaintenanceEventStatus` SQLAlchemy model uses lowercase values (`planned`, `in_progress`, `done`, `missed`, `cancelled`). When `admin_dashboard` queried `MaintenanceEventStatus.PLANNED`, SQLAlchemy sent `'planned'` to Postgres which rejected it with HTTP 500 `DataError`.
   - **Failing File & Line**: `alembic/versions/4573d757029f_initial_schema.py:108` and `app/routers/web.py:116` (`admin_dashboard` route querying `MaintenanceEvent.status`).
   - **Fix**: Created a new Alembic migration `77a8b9c0d1e2_fix_enum_values.py` that alters the `maintenanceeventstatus` enum type in Postgres to use lowercase string values (`planned`, `in_progress`, `done`, `missed`, `cancelled`) matching the ORM model, and updated `4573d757029f_initial_schema.py` for fresh database builds.

2. **Issue 2 — Missing Audit Log Viewer Route (`/admin/audit`)**:
   - **URL**: `http://localhost:8000/admin/audit`
   - **Role**: `ADMIN`
   - **HTTP Method**: `GET`
   - **Root Cause**: The audit log view endpoint requirement was missing from router registration.
   - **Fix**: Implemented `/admin/audit` in `app/routers/admin.py` and template `app/templates/admin/audit.html`.

3. **Issue 3 — Unauthenticated Web Requests Handling**:
   - **URL**: `http://localhost:8000/` & `/admin/dashboard` (when unauthenticated)
   - **Role**: `ANONYMOUS`
   - **HTTP Method**: `GET`
   - **Root Cause**: Unauthenticated HTML page visits raised `HTTPException(401)` which returned raw 401 JSON instead of redirecting the browser to `/auth/login`.
   - **Fix**: Added exception handler in `app/main.py` redirecting 401 HTML requests with `302 Found` to `/auth/login`.

## 2. Verification & Smoke Testing

- Added unit/integration tests in `tests/test_hotfixes.py` verifying `/admin/dashboard` access for `ADMIN` (HTTP 200), redirect on `GET /` (HTTP 302 -> `/admin/dashboard`), and 403 / redirect behavior for `TECHNICIAN` and `USER` roles.
- Configured CI E2E Docker Compose smoke test in `.github/workflows/ci.yml` that boots the container stack (`docker compose up -d`), waits for web health, logs in as `ADMIN`, and asserts HTTP 200/302 on all Iteration 2 pages.

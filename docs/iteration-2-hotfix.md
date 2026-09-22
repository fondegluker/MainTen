# Iteration 2 Hotfix Diagnosis & Audit Report

## 1. Summary of Reproduced Issues & Root Causes

During runtime audit and reproduction against Iteration 2 requirements (§5.1, §9):

1. **Issue 1 — Missing Audit Log Viewer Route (`/admin/audit`)**:
   - **URL**: `http://localhost:8000/admin/audit`
   - **Role**: `ADMIN`
   - **HTTP Method**: `GET`
   - **Error / Traceback**:
     ```
     HTTP 404 Not Found
     ```
   - **Root Cause**: The audit log view endpoint requirement (§5.1 & §9 item 5) was omitted from the router registration in `app/routers/admin.py` and template `app/templates/admin/audit.html`.
   - **Failing File & Line**: `app/routers/admin.py` (missing `@router.get("/audit")`).

2. **Issue 2 — Missing Unauthenticated Web HTML Redirect Handling**:
   - **URL**: `http://localhost:8000/admin/dashboard` (when unauthenticated via browser)
   - **Role**: `ANONYMOUS`
   - **HTTP Method**: `GET`
   - **Error / Traceback**:
     ```
     {"detail":"Not authenticated"} (HTTP 401 JSON Response)
     ```
   - **Root Cause**: Unauthenticated browser visits to HTML page routes raised a FastAPI `HTTPException(status_code=401)`, returning raw JSON instead of redirecting the user to `/auth/login`.
   - **Failing File & Line**: `app/auth/dependencies.py:23` (`get_current_user` raised `HTTPException(401)`).

3. **Issue 3 — Database Connection Failure on Host without Running PostgreSQL Service**:
   - **URL**: `http://localhost:8000/admin/dashboard` & `/auth/login`
   - **Role**: `ADMIN` / `ANONYMOUS`
   - **HTTP Method**: `POST` / `GET`
   - **Exact Traceback**:
     ```
     psycopg2.OperationalError: connection to server at "localhost" (::1), port 5432 failed: Connection refused
     Is the server running on that host and accepting TCP/IP connections?
     ```
   - **Root Cause**: When running the web app directly on local host without PostgreSQL running, the default `DATABASE_URL` in `app/core/config.py` attempted to connect to `postgresql://...` on localhost:5432 and failed with `psycopg2.OperationalError` (HTTP 500).
   - **Failing File & Line**: `app/core/database.py` / `app/routers/web.py:76` (database connection initialization).

## 2. Implemented Fixes

1. **Audit Log Viewer**:
   - Added `GET /admin/audit` in `app/routers/admin.py` with filterable action/entity search, pagination, and Jinja2 rendering template `app/templates/admin/audit.html`.

2. **Unauthenticated Web HTML Redirect**:
   - Added `HTTPException` exception handler in `app/main.py` that intercepts `401 Unauthorized` requests containing `text/html` in `Accept` headers and issues a `302 Found` redirect to `/auth/login`.

3. **Database Environment Fallback**:
   - Ensured database connection errors fail gracefully, and provided environment variable overrides.

4. **GitHub Actions E2E Container Smoke Test**:
   - Updated `.github/workflows/ci.yml` to build and start containers via `docker compose up -d`, wait for web health on `http://localhost:8000`, log in as `ADMIN`, and exercise all Iteration 2 URLs asserting HTTP 200 responses.

# Event Detail Page HTTP 500 Hotfix

## Request Context
- **Method:** GET
- **Path:** `/technician/events/{id}` (e.g., `GET /technician/events/6`)
- **User Role:** `TECHNICIAN` (or any authenticated user accessing the route)

## Reproduction Steps with Seed
```bash
docker compose down -v
./run.sh
# or: python -m app.seed_demo
```

## Verbatim Traceback & Root Causes
1. **`TemplateSyntaxError` from JS quote escaping:**
   ```text
   File "app/templates/technician/event_detail.html", line 292, in template
       <img src="/technician/events/{{ event.id }}/attachments/{{ img.id }}" alt="{{ img.filename }}" onerror="this.onerror=null; this.parentElement.onclick=null; this.parentElement.className='...'; this.parentElement.innerHTML='<span class=\'font-bold text-3xs truncate\'>{{ img.filename }}</span>...';" ...>
   jinja2.exceptions.TemplateSyntaxError: unexpected char '\' at 20908
   ```
   *Root Cause:* Escaped single quotes (`\'`) inside an inline HTML `onerror="..."` attribute broke Jinja's parser because Jinja does not treat `\` as an escape character in raw template text.

2. **`UndefinedError: 'hasattr' is undefined`:**
   *Root Cause:* `hasattr` is a Python built-in function and is not available in Jinja2 template context. Attempting to call `hasattr(user.role, 'value')` raised an `UndefinedError`.

3. **Empty attachment lists from mutation syntax:**
   *Root Cause:* Calling `{% set _ = list.append(...) %}` in Jinja does not mutate list variables across loop iterations as expected.

## Fixes Applied
1. **`app/templates/technician/event_detail.html`**:
   - Replaced inline `onerror="..."` handler with `data-fallback-filename` and `data-fallback-msg` attributes on `<img>` elements, handled via a DOM `addEventListener('error')` script.
   - Removed all occurrences of `hasattr` and replaced with standard attribute checks/variable assignments at the top level of `{% block content %}`.
   - Removed `{% set _ = list.append(...) %}` syntax.
2. **`app/seed_demo.py`**:
   - Removed invalid `created_at` keyword argument from `Computer(...)` constructor.
   - Set `is_done=False` on `MaintenanceEventCheck` instances to adhere to PostgreSQL `NOT NULL` constraints.
3. **Permanent Guards & Tests**:
   - **`tests/unit/test_templates_compile.py`**: Added permanent template compile smoke test `test_all_templates_compile()` to verify every `.html` template under `app/templates/` compiles cleanly without Jinja syntax errors.
   - **`tests/integration/test_event_detail_renders.py`**: Added regression test verifying `GET /technician/events/{id}` returns HTTP 200 across `PLANNED`, `IN_PROGRESS`, `DONE`, and `MISSED` event statuses for assigned technicians and admins, and enforces HTTP 403 for unassigned roles.

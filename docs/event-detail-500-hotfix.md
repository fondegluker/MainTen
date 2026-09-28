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

## Verbatim Traceback
```text
File "app/templates/technician/event_detail.html", line 292, in template
    <img src="/technician/events/{{ event.id }}/attachments/{{ img.id }}" alt="{{ img.filename }}" onerror="this.onerror=null; this.parentElement.onclick=null; this.parentElement.className='...'; this.parentElement.innerHTML='<span class=\'font-bold text-3xs truncate\'>{{ img.filename }}</span>...';" ...>
jinja2.exceptions.TemplateSyntaxError: unexpected char '\' at 20908
```

## Root Cause
The `onerror="..."` attribute on the attachment `<img>` element in `app/templates/technician/event_detail.html` used JS-style single quote escapes (`\'`). Jinja2's parser does not treat `\` as an escape character in raw template text, resulting in a `jinja2.exceptions.TemplateSyntaxError` at parse time whenever the template was loaded.

## Fix Applied
1. **`app/templates/technician/event_detail.html`**:
   - Removed the inline `onerror="..."` attribute containing `\'` escapes.
   - Added `data-fallback-filename="{{ img.filename }}"` and `data-fallback-msg="{{ t('file_missing_on_server') }}"` attributes to the `<img>` tag.
   - Added a clean DOM event listener (`addEventListener('error')`) in a `<script>` block to safely create fallback elements using `document.createElement('span')` without string escapes.
2. **`app/seed_demo.py`**:
   - Removed invalid `created_at` keyword argument from `Computer(...)` constructor.
   - Changed `is_done=None` to `is_done=False` on `MaintenanceEventCheck` instances to adhere to the NOT NULL column constraint.
3. **`tests/unit/test_templates_compile.py`**:
   - Added permanent template compilation smoke test `test_all_templates_compile()` to verify every `.html` template under `app/templates/` compiles cleanly via Jinja2.

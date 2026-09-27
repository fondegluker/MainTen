# Event Detail Page HTTP 500 Hotfix

## Request Context
- **Method:** GET
- **Path:** `/technician/events/{id}` (e.g., `GET /technician/events/6`)
- **User Role:** `TECHNICIAN` (or any authenticated user accessing the route)

## Verbatim Traceback
```text
File "app/templates/technician/event_detail.html", line 206, in template
    {% endif %}
jinja2.exceptions.TemplateSyntaxError: Encountered unknown tag 'endif'. You probably made a nesting mistake. Jinja is expecting this tag, but currently looking for 'endfor'. The innermost block that needs to be closed is 'for'.
```

## Root Cause
A stray `{% endif %}` tag was present inside the protocol items `{% for item in protocol_items %}` loop in `app/templates/technician/event_detail.html`. Because the tag was unclosed before line 206, Jinja failed to parse the `{% for %}` loop, causing a `jinja2.exceptions.TemplateSyntaxError` whenever `event_detail.html` was evaluated and resulting in an HTTP 500 Internal Server Error.

## Failing Location & Fix
- **File:** `app/templates/technician/event_detail.html`
- **Location:** Line 188
- **Fix:** Removed the stray `{% endif %}` tag to restore balanced `{% for ... %}` / `{% endfor %}` and `{% if ... %}` / `{% endif %}` nesting. Added a Jinja template compilation smoke test `test_template_compile_smoke` in `tests/integration/test_event_detail_hotfix.py`.

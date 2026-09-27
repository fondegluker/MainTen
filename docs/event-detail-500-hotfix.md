# Event Detail Page HTTP 500 Hotfix

## Request Context
- **Method:** GET
- **Path:** `/technician/events/{id}` (e.g., `GET /technician/events/6`)
- **User Role:** `TECHNICIAN` (or any authenticated user accessing the route)

## Verbatim Traceback
```text
Traceback (most recent call last):
  File "/usr/local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 164, in __call__
    await self.app(scope, receive, _send)
  File "/usr/local/lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
    await self.app(scope, receive, send)
  File "/usr/local/lib/python3.12/site-packages/fastapi/applications.py", line 1054, in __call__
    await self.app(scope, receive, send)
  File "/usr/local/lib/python3.12/site-packages/starlette/routing.py", line 718, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/usr/local/lib/python3.12/site-packages/starlette/routing.py", line 738, in app
    await route.handle(scope, receive, send)
  File "/usr/local/lib/python3.12/site-packages/starlette/routing.py", line 276, in handle
    await self.app(scope, receive, send)
  File "/usr/local/lib/python3.12/site-packages/starlette/routing.py", line 66, in app
    response = await func(request)
  File "/usr/local/lib/python3.12/site-packages/fastapi/routing.py", line 291, in app
    solved_result = await solve_dependencies(
  File "/usr/local/lib/python3.12/site-packages/fastapi/dependencies/utils.py", line 623, in solve_dependencies
    solved = await run_in_threadpool(call, **solved_kwargs)
  File "/usr/local/lib/python3.12/site-packages/starlette/concurrency.py", line 35, in run_in_threadpool
    return await anyio.to_thread.run_sync(func, *args)
  File "/usr/local/lib/python3.12/site-packages/anyio/_backends/_asyncio.py", line 226, in run_sync
    return func(*args)
  File "/app/app/routers/technician.py", line 38, in _check_event_access
    if user.role.value in ["admin", "ADMIN"]:
       ^^^^^^^^ font AttributeError: 'str' object has no attribute 'value'
```

## Root Cause
The `_check_event_access` helper function assumed `user.role` was always an instance of `UserRole` Enum (which has a `.value` attribute), but depending on ORM loading / mock construction, `user.role` can be stored as a raw string (e.g., `'technician'`), causing `user.role.value` to raise an `AttributeError: 'str' object has no attribute 'value'`.

## Failing Location
- **File:** `app/routers/technician.py`
- **Line:** 38 (in `_check_event_access`)

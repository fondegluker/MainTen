# Project: Computer Fleet Maintenance Scheduler (CFMS)

You are a senior full-stack engineer. Build a production-ready web application
for scheduling and tracking preventive maintenance (ТО) of a corporate
computer fleet. Follow every requirement below strictly. When a choice is
not specified, pick a mainstream, well-documented, boring technology — do not
invent exotic solutions.

Deliver the work in ITERATIONS (see the end of this prompt). Each iteration
must ship with passing tests, updated docs, and be runnable end-to-end.
Never mix more than one iteration into a single commit/PR.

---

## Global iteration requirements (apply to EVERY iteration)
Each iteration must satisfy ALL of the following, in addition
to its own scope:
- unit + integration tests green,
- `ruff check .` and `ruff format --check .` clean,
- `import-smoke` green,
- `e2e-smoke` green (see CONTRIBUTING.md for the exact scope),
- README + docs/decisions.md updated,
- no branch operations by the agent; work stays in the current
  branch; never push to `main`.

An iteration is not "done" until these are all true. Do not
treat any of them as optional or as "later work".

---

## 1. Tech stack (you choose, but respect these constraints)

- Backend: any mainstream stack with a strong ORM + migrations ecosystem.
  Suggested: Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic.
- Frontend: server-rendered pages are preferred for simplicity
  (Jinja2 + HTMX + Tailwind + Alpine.js is a good fit).
  A SPA is acceptable only if you justify it.
- Database: PostgreSQL 16.
- Auth: local username/password (argon2 or bcrypt) for ADMIN and TECHNICIAN.
  USERS authenticate via signed magic-link tokens stored in secure cookies.
  Design an abstraction so an AD/LDAP provider can be plugged in later
  (no AD present today — implement a `LocalAuthProvider` now, stub
  `AdAuthProvider` with a clear interface).
- Deployment: Docker + docker-compose for production; systemd unit files
  also provided for dev. Single host.
- UI: modern, clean, responsive (desktop-first). Use TailwindCSS + a
  component library (shadcn-style or Flowbite). Dark mode is optional.
- i18n: Russian (default) + English. Use a standard i18n library
  (e.g. Babel for Python or i18next for JS). All user-facing strings
  must go through the translation layer.
- Testing: unit + integration tests for every module. CI via GitHub Actions
  running `pytest` (or equivalent) and linting on every push.

## 2. Roles and users

- ADMIN — full access to configuration, users, computers, protocol,
  reports, network scan, import.
- TECHNICIAN — sees own daily schedule, fills maintenance cards,
  receives escalations.
- USER — end user tied to a computer. Authenticates via token link.
  Can pick a maintenance date and view own PC history.
- OBSERVER — read-only access to reports (e.g. management).
- "Manager" is NOT a role; it is a virtual property of a USER who has
  more than one computer assigned. The user page must aggregate
  multiple computers for such a user.

## 3. Data model (minimum)

- `users` (id, username, email_or_login, password_hash, role, locale,
  is_active, created_at)
- `computers` (id, hostname, ip, mac, os, location/room, owner_user_id,
  is_round_the_clock BOOL, last_maintenance_at, next_maintenance_due_at,
  status, notes)
- `maintenance_protocol_items` (id, order_index, title_ru, title_en,
  description, is_active, created_at, updated_at)
- `maintenance_events` (id, computer_id, technician_id, scheduled_date,
  scheduled_slot, status enum: planned|in_progress|done|missed|cancelled,
  started_at, finished_at, comment, created_at, updated_at)
- `maintenance_event_checks` (id, event_id, protocol_item_id, is_done BOOL,
  comment, checked_at)
- `maintenance_event_attachments` (id, event_id, filename, mime, blob_path,
  uploaded_at)
- `notifications` (id, user_id, computer_id, event_id, channel,
  payload_json, sent_at, acknowledged_at)
- `audit_log` (id, actor_user_id, action, entity, entity_id,
  before_json, after_json, created_at)
- `settings` (key, value_json) — single-row config table for intervals,
  notification window, SMTP, calendar, etc.

All historical maintenance records are kept forever. Never hard-delete
maintenance_events or event_checks; use status transitions.

## 4. Business logic

### 4.1 Scheduling

- Default intervals: ROUND_THE_CLOCK computers → every 6 months;
  others → every 12 months. Both intervals are configurable in settings.
- `next_maintenance_due_at` = last completed maintenance + interval.
- "Notification window" = configurable, default 20 days before due date.
  During this window, the user is prompted to choose a date.
- Available dates for the user:
  - only future dates;
  - only working days per Belarus production calendar
    (Mon–Fri, excluding Belarusian public holidays);
  - the date must be free for the assigned technician
    (technician may perform at most 1 maintenance per day);
  - window length is configurable (default 20 days, but the picker
    should show the next N working days that are free).
- The user picks a date → a `maintenance_event` is created with status
  `planned` and assigned to a technician.
- If the user does NOT pick a date within the window:
  - send a daily reminder to the user via the local agent;
  - escalate to the technician and the admin;
  - after the window expires, shift the "it's time to choose" moment
    forward by one month and repeat.
- Technicians can create out-of-schedule (unplanned) events manually.
- Changing or cancelling an event must be recorded in `audit_log`.

### 4.2 Maintenance execution

- A technician opens their day view. Each event is a card with the full
  protocol checklist. For each protocol item, the technician marks a
  checkbox (done / not done) and may add a comment.
- Attachments (photos, files) are allowed per event.
- On finish, the event transitions to `done`, `last_maintenance_at`
  and `next_maintenance_due_at` for the computer are recalculated.

### 4.3 Notifications

- ONLY channel: a locally-installed Windows agent
  (installed as a Windows service). Email is explicitly out of scope.
- The agent polls the backend (or receives push via WebSocket) and
  shows a Windows toast with a clickable link that opens the
  user-specific date-picker page for the specific computer.
- The notification target is always the specific user bound to the
  specific computer — never broadcast.
- Notifications must also be sent to technicians (daily schedule
  digest) and admins (escalations, missed events).
- Reminders to the user are sent once per day until a date is chosen.
- Every notification is stored in `notifications` for auditability.
- Provide a working Windows agent project (C#/.NET or Python + pywin32)
  with an MSI/EXE installer and clear installation docs.

## 5. Pages

### 5.1 Admin
- Dashboard with key stats.
- CRUD for users, computers, technicians, observers.
- Protocol editor: add/edit/delete/reorder/enable/disable items,
  RU + EN titles.
- Settings page: intervals, notification window, working calendar,
  Belarusian holidays, technician daily capacity (default 1).
- Import fleet from Excel (xlsx) with preview and validation.
- Network scanner wizard: scan a subnet, detect hosts, pre-fill the
  computers table with hostname/IP/OS when possible, let admin review
  and confirm. Support re-running the scan to detect new devices.
- Audit log viewer (filterable).

### 5.2 User
- "Choose maintenance date" page: calendar with only selectable free
  working days in the notification window.
- "My computer" page: hostname, IP, OS, location, last maintenance
  date, status of last maintenance, full history of past events
  with checklists.
- If the user owns multiple computers (manager case), show all of
  them with per-computer pickers.

### 5.3 Technician
- Day view (default = today) with one card per scheduled event.
- Week view.
- Event detail page: protocol checklist, comments, attachments,
  "Start" / "Finish" buttons, ability to mark as missed with a reason.
- Ability to create an unplanned event for a specific computer.

### 5.4 Reports (also visible to OBSERVER, read-only)
- Overdue maintenance.
- Technician load per day/week/month.
- Fleet stats: total computers, RTC vs non-RTC, done this period,
  missed this period, upcoming.
- Timeline / Gantt of scheduled maintenance.
- Configurable charts (bar, pie, line) with date-range filters.
- Export to Excel / CSV / PDF.
- User activity log (login, date pick, notifications received).

## 6. Non-functional

- Fleet size target: ~300 computers. Concurrent users: ~30.
  Design for this scale — no premature optimization, but avoid
  obviously quadratic queries.
- HTTPS in production (reverse proxy is fine).
- No 152-FZ / GDPR-specific compliance required, but store passwords
  hashed and never log secrets.
- Backups: out of scope for v1, but expose a documented `pg_dump`
  helper script.
- Log every mutating action to `audit_log`.
- Mobile version is NOT required (desktop-first responsive is enough).

## 7. Repository & process

- Repo already exists on GitHub. Push all work there.
- Provide a `README.md` with: architecture overview, DB schema diagram
  (Mermaid), setup instructions (docker + systemd), and a "how to run
  tests" section.
- Provide OpenAPI spec for the backend (auto-generated is fine).
- GitHub Actions: lint + tests on every push and PR.
- Every iteration must end with a green CI and a working
  `docker-compose up`.

## 8. Iterations (do them strictly in this order)

**Iteration 1 — Skeleton.**
Repo layout, backend bootstrap, PostgreSQL via docker-compose,
Alembic migrations for the full schema from §3, settings table,
local auth for ADMIN/TECHNICIAN, magic-link auth for USER,
basic layout with i18n (ru/en), empty admin dashboard.
Tests: auth flows, migrations apply cleanly.

**Iteration 2 — Admin CRUD + Excel import.**
Users, computers, technicians CRUD. Excel import with preview.
Audit log table populated. Tests for CRUD and import.

**Iteration 3 — Protocol editor + settings.**
Protocol items CRUD with ordering and RU/EN titles.
Settings page for intervals, notification window, capacity,
Belarus calendar. Tests for settings validation.

**Iteration 4 — Scheduling engine + user page.**
Compute `next_maintenance_due_at`. Open the notification window.
User page with the date picker (working days, free technician
slots, future only). Create `maintenance_event`. Tests for
the scheduling rules (RTC vs non-RTC, window, escalation timing).

**Iteration 5 — Technician pages.**
Day/week views, event card with protocol checklist, comments,
attachments, start/finish transitions, unplanned events.
Tests for status transitions and recalculation of next due date.

**Iteration 6 — Notifications + Windows agent.**
Backend notification service, `notifications` table persistence,
API for the agent. Windows agent project (service + toast + clickable
link). Daily reminders, escalations. Tests for notification rules
(idempotency per day, escalation triggers).

**Iteration 7 — Reports + observer role.**
All reports from §5.4, filters, charts, exports, activity log.
Observer role wired to read-only views. Tests for report queries.

**Iteration 8 — Network scanner wizard.**
Subnet scan, host discovery, OS/hostname detection, review UI,
merge into computers table. Tests with mocked scan results.

**Iteration 9 — Hardening.**
Rate limiting, error pages, structured logging, final README
polish, demo seed data, end-to-end smoke test in CI.

Each iteration must:
1. Update the README with what was added.
2. Keep `docker-compose up` working from a clean checkout.
3. Pass all tests in CI.
4. Not break previous iterations.

Start with Iteration 1 only. Do not proceed to Iteration 2 until
Iteration 1 is committed, CI is green, and the app runs locally.

If any requirement is ambiguous, choose the simplest reasonable
interpretation, document the decision in `docs/decisions.md`,
and continue. Do not stop to ask questions unless the decision
would be irreversible.

# Project: MainTen — Computer Fleet Maintenance Scheduler

You are a senior full-stack engineer. Build a production-ready web application
for scheduling and tracking preventive maintenance (ТО) of a corporate
computer fleet. Follow every requirement below strictly. When a choice is
not specified, pick a mainstream, well-documented, boring technology — do not
invent exotic solutions.

This project lives in the GitHub repository **MainTen**.
The Windows notification agent lives in a SEPARATE repository
**MainTen-Agent**. Do NOT put agent code inside MainTen. Only the agent's
backend API contract is defined here (see §4.4).

Deliver the work in ITERATIONS (see §9). Each iteration must ship with
passing tests, updated docs, and be runnable end-to-end.
Never mix more than one iteration into a single commit/PR.

---

## 1. Tech stack

- Backend: any mainstream stack with a strong ORM + migrations ecosystem.
  Suggested: Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic.
- Frontend: server-rendered pages preferred
  (Jinja2 + HTMX + Tailwind + Alpine.js).
- Database: PostgreSQL 16.
- Auth:
  - local username/password (argon2) for ADMIN and TECHNICIAN;
  - USERS authenticate via signed magic-link tokens in secure cookies;
  - design an `AuthProvider` abstraction so `AdAuthProvider` can be
    plugged in later (no AD today — ship `LocalAuthProvider` only).
- Deployment: Docker + docker-compose (production and dev).
  Single host. systemd units also provided for local dev.
- UI: modern, clean, responsive (desktop-first).
  TailwindCSS + a component library (shadcn-style or Flowbite).
- i18n: Russian (default) + English, via a standard library.
  All user-facing strings go through the translation layer.
- Testing: unit + integration tests for every module.
  GitHub Actions runs lint + tests on every push and PR.
- The container image MUST include `nmap` and `arp-scan` so the
  network scanner wizard (see §5.1) works inside Docker.
  The scanner container may run with `--network host`; document this
  in the README and in docker-compose.

## 2. Roles

- ADMIN — configuration, users, computers, protocol, reports,
  network scan, import.
- TECHNICIAN — own daily schedule, maintenance cards, escalations.
- USER — end user tied to a computer; authenticates via token link;
  picks a maintenance date; views own history.
- OBSERVER — read-only access to reports.
- "Manager" is NOT a role; it is a virtual property of a USER who has
  more than one computer assigned. The user page aggregates their
  computers.

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
- `settings` (key, value_json) — single-row config table.
- `working_calendar` (id, date, is_working BOOL, kind enum:
  workday|weekend|holiday|short_day, note_ru, note_en, source enum:
  default|seed|admin) — fully editable by ADMIN.
- `holidays` may be folded into `working_calendar`; do not create a
  duplicate table.

All historical maintenance records are kept forever. Never hard-delete
`maintenance_events` or `event_checks`; use status transitions.

## 4. Business logic

### 4.1 Intervals

- Default: RTC computers → every 6 months; others → every 12 months.
- Both intervals are configurable in settings.
- `next_maintenance_due_at` = last completed maintenance + interval.
  This is the "trigger date".

### 4.2 Selection window and prompt start (IMPORTANT)

Two independent settings, both configurable by ADMIN:

- `selection_window_days` — how many days BEFORE the trigger date the
  user is allowed to pick a date. Default = 20.
- `prompt_start_offset_days` — how many days BEFORE the trigger date
  the user starts receiving daily prompts. Default = half of
  `selection_window_days` (i.e. 10 when window = 20).

**Worked example (must be covered by an automated test):**
- Computer is non-RTC → interval = 12 months.
- Last maintenance done on **2025-09-23**.
- Trigger date = **2026-09-23**.
- `selection_window_days = 20` → the user may pick a date in the
  range **[2026-09-03 .. 2026-09-23]** (working days only, see §4.3).
- `prompt_start_offset_days = 10` → the user first receives the
  prompt on **2026-09-13**, then daily until a date is chosen or the
  window expires.
- If the user does not pick a date by the end of the window →
  escalate to technician and admin; shift the "time to choose"
  moment forward by one month and repeat.

The prompt-start rule must be implemented as:
`prompt_start_date = trigger_date - prompt_start_offset_days`
and NOT simply "start at the beginning of the window".

### 4.3 Date picker rules

Available dates for the user:
- only future dates (strictly > today);
- only working days per the **editable Belarus working calendar**
  (see §5.1);
- the assigned technician must be free
  (default max 1 maintenance per day per technician);
- the date must fall within `[trigger_date - selection_window_days .. trigger_date]`;
- the picker shows only the N nearest free working days that satisfy
  the above; N is derived from the window, not hardcoded.

On pick: create `maintenance_event` (status `planned`) with a technician.
On window expiry without a pick: escalation + shift by one month.
Changing or cancelling an event must be recorded in `audit_log`.

### 4.4 Technician execution

- Day and week views; each event is a card with the full protocol
  checklist. Per protocol item: checkbox (done / not done) + comment.
- Attachments (photos/files) allowed per event.
- Transitions: `planned → in_progress → done` (or `missed` with reason).
- On `done`: recalculate `last_maintenance_at` and
  `next_maintenance_due_at` for the computer.
- Technicians can create out-of-schedule (unplanned) events manually.

### 4.5 Notifications (backend contract only)

- Only channel: the **MainTen-Agent** Windows service running on the
  user's PC. Email is explicitly out of scope.
- The backend exposes a stable API contract for the agent (see below).
  The agent implementation lives in the **MainTen-Agent** repository —
  do NOT implement agent code inside MainTen.
- Every notification is persisted in `notifications` for auditability.
- Reminders to the user are sent once per day until a date is chosen.
- Notifications to technicians: daily schedule digest.
- Notifications to admins: escalations, missed events.
- Notification target is always the specific user bound to the
  specific computer — never a broadcast.

**Agent backend contract (freeze this early, version it):**
- `POST /api/agent/register` — agent registers a machine with a token;
  returns an `agent_id` + polling interval.
- `GET  /api/agent/{agent_id}/pending` — returns pending notifications
  (with clickable deep-link URL to the user's date-picker page).
- `POST /api/agent/{agent_id}/ack` — acknowledge receipt / click.
- `GET  /api/agent/health` — liveness.
- Auth: mutual token (agent token issued by admin, stored server-side
  hashed). All responses JSON. OpenAPI documented.

## 5. Pages

### 5.1 Admin
- Dashboard with key stats.
- CRUD for users, computers, technicians, observers.
- Protocol editor: add/edit/delete/reorder/enable/disable items,
  RU + EN titles.
- **Working calendar editor (fully editable):**
  - list view by month;
  - toggle any date as working / non-working;
  - mark holidays and short days with RU/EN notes;
  - bulk import of a year's calendar (CSV/JSON);
  - "reset to default Belarus calendar" action
    (defaults are seeded, not hardcoded);
  - all changes are written to `working_calendar` with
    `source = admin` and logged in `audit_log`.
- Settings page: intervals (6/12 by default), `selection_window_days`,
  `prompt_start_offset_days`, technician daily capacity (default 1),
  agent token issuance.
- Import fleet from Excel (xlsx) with preview and validation.
- **Network scanner wizard** (uses `nmap` inside the container):
  - scan a subnet, detect live hosts, OS and hostname when possible;
  - pre-fill the computers table;
  - admin reviews and confirms;
  - re-run supported to detect new devices;
  - document `--network host` requirement in README.
- Audit log viewer (filterable).

### 5.2 User
- "Choose maintenance date" page: calendar showing only selectable
  free working days inside the window.
- "My computer" page: hostname, IP, OS, location, last maintenance,
  status, and full history with checklists.
- If the user owns multiple computers, show all with per-computer
  pickers.

### 5.3 Technician
- Day view (default today) with one card per event.
- Week view.
- Event detail: checklist, comments, attachments, Start/Finish,
  Mark-as-missed with reason.
- Create unplanned event for a specific computer.

### 5.4 Reports (also visible to OBSERVER, read-only)
- Overdue maintenance.
- Technician load per day/week/month.
- Fleet stats (total, RTC vs non-RTC, done/missed/upcoming this period).
- Timeline / Gantt of scheduled maintenance.
- Configurable charts (bar, pie, line) with date-range filters.
- Export to Excel / CSV / PDF.
- User activity log (login, date pick, notifications received).

## 6. Non-functional

- Target: ~300 computers, ~30 concurrent users.
- HTTPS in production (reverse proxy is fine).
- Store passwords hashed; never log secrets.
- Backups: out of scope for v1; provide a documented `pg_dump` helper.
- Every mutating action is written to `audit_log`.
- Mobile version is not required (desktop-first responsive is enough).

## 7. Repositories

- **MainTen** (this repo) — the web application.
  Must include: architecture overview in README, Mermaid DB schema
  diagram, setup (docker + systemd), "how to run tests", OpenAPI spec.
- **MainTen-Agent** (separate repo, out of scope here) —
  Windows service + toast notifications + clickable deep-links.
  MainTen only defines and implements the backend API contract
  from §4.5. Document the contract in `docs/agent-api.md`.

## 8. Process

- GitHub Actions: lint + tests on every push and PR.
- Every iteration ends with a green CI and a working
  `docker-compose up` from a clean checkout.
- If a requirement is ambiguous: choose the simplest reasonable
  interpretation, write it to `docs/decisions.md`, continue.
  Do not stop to ask questions unless the decision is irreversible.

## 9. Iterations (strict order)

**Iteration 1 — Skeleton.** ✅ (already done by the user)
Repo layout, backend bootstrap, PostgreSQL via docker-compose,
Alembic migrations for the full schema from §3 (including
`working_calendar`), settings table, local auth for ADMIN/TECHNICIAN,
magic-link auth for USER, basic layout with i18n (ru/en), empty admin
dashboard. Tests: auth flows, migrations apply cleanly.

**Iteration 2 — Admin CRUD + Excel import.**
Users, computers, technicians CRUD. Excel import with preview.
Audit log populated. Tests for CRUD and import.

**Iteration 3 — Protocol editor + settings + calendar editor.**
Protocol items CRUD with ordering and RU/EN titles.
Settings page for intervals, `selection_window_days`,
`prompt_start_offset_days`, technician capacity.
Full **working calendar editor** (CRUD, seed defaults for Belarus,
bulk import, reset). Tests for settings validation and calendar
edit audit trail.

**Iteration 4 — Scheduling engine + user page.**
Compute `next_maintenance_due_at` (trigger date).
Implement prompt-start rule from §4.2 and cover the worked example
with a test. User page with the date picker (working days, free
technician slots, future only, window bounds). Create
`maintenance_event`. Tests for RTC vs non-RTC, window math,
prompt-start offset, escalation timing.

**Iteration 5 — Technician pages.**
Day/week views, event card with checklist, comments, attachments,
start/finish transitions, unplanned events. Tests for status
transitions and recalculation of next due date.

**Iteration 6 — Notifications API + agent contract.**
Notification service, `notifications` persistence, API from §4.5,
`docs/agent-api.md`, daily reminders, escalations, idempotency per
day. Tests for notification rules. NO agent code inside MainTen —
that lives in MainTen-Agent.

**Iteration 7 — Reports + observer role.**
All reports from §5.4, filters, charts, exports, activity log.
Observer role wired to read-only views. Tests for report queries.

**Iteration 8 — Network scanner wizard.**
nmap-based subnet scan inside the container
(`--network host` documented), host discovery, OS/hostname detection,
review UI, merge into computers table, re-run to detect new devices.
Tests with mocked scan results.

**Iteration 9 — Hardening.**
Rate limiting, error pages, structured logging, README polish,
demo seed data, end-to-end smoke test in CI.

Each iteration must:
1. Update README with what was added.
2. Keep `docker-compose up` working from a clean checkout.
3. Pass all tests in CI.
4. Not break previous iterations.

Start with Iteration 2 only. Do not proceed to Iteration 3 until
Iteration 2 is committed, CI is green, and the app runs locally.

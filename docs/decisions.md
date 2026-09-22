# Architectural Decisions & Design Rationale

## Tech Stack Decisions

### Backend: FastAPI + SQLAlchemy 2.0 + Alembic + Python 3.12
- **Rationale**: Selected Python 3.12 with FastAPI and SQLAlchemy 2.0. FastAPI provides high performance, automatic OpenAPI documentation, and clear async/sync request handling capabilities. SQLAlchemy 2.0 provides type-safe ORM mappings and Alembic manages database schema evolution seamlessly.

### Frontend: Server-Rendered Jinja2 + HTMX + Tailwind CSS + Alpine.js
- **Rationale**: Server-side rendering (SSR) avoids unnecessary SPA complexity for administrative workflow tools, providing instant page load times, straightforward i18n rendering, and simple cookie-based authentication handling.

### Database: PostgreSQL 16
- **Rationale**: Robust, battle-tested transactional relational database supporting JSON data types for flexible configurations (`settings`, `audit_log`, `notifications.payload_json`).

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

# Contributing Guidelines & Working Branch Model

This repository follows a **single long-lived working-branch model** for development, with manual maintainer snapshotting for release bookkeeping.

---

## Definition of Done for EVERY iteration

Every iteration, without exception, must ship with:
1. Before committing and before marking the task complete, run `./scripts/check.sh` and confirm it exits with code 0. Paste the last 20 lines of its output in the final summary. The task is NOT complete until this is done. Do not mark the task done if the script reports any errors.
2. All unit and integration tests green.
3. `ruff check .` and `ruff format --check .` clean.
3. `import-smoke` green (all `app/` modules importable).
4. **`e2e-smoke` green** — a real browser walks every role through every nav link, asserts no 404/500, toggles the locale, and follows a magic-link through to a working date picker.
5. README and `docs/decisions.md` updated.
6. No new branch created; work stays in the current branch.

If `e2e-smoke` is not green, the iteration is NOT done, no matter what the other tests say. This rule is mandatory and must not be skipped or deferred to a "later iteration".

---

## Linting & Formatting

Run `./scripts/check.sh` before every commit. CI runs the same sequence (without `--fix`).

```bash
# Pre-flight check script
./scripts/check.sh

# Or run linter & formatter directly
ruff check . --fix && ruff format .
```

To automatically run linter checks on `git commit`, install pre-commit:

```bash
pip install pre-commit && pre-commit install
```

CI automatically runs `ruff check .` and `ruff format --check .` on every push and pull request. PRs with linting or formatting errors will be rejected by CI. Note: ruff rule BLE001 (blind Exception catch) is strictly enforced; any `# noqa: BLE001` override requires explicit justification.

---

## How to run e2e locally

To run the end-to-end smoke test suite locally:

1. **Start the application stack**:
   ```bash
   docker compose up -d --build
   # OR start background server:
   # uvicorn app.main:app --port 8000
   ```
2. **Execute the E2E Playwright smoke suite**:
   ```bash
   pytest tests/e2e/ -x -q
   ```
3. **Inspect failure artifacts**:
   In case of a failure, inspect `artifacts/app.log` or container logs via `docker compose logs web`.

---

## Standard prompt for starting an iteration

When starting any iteration, copy this template verbatim:

```
Read docs/requirements.md and CONTRIBUTING.md.
Implement Iteration <N> ONLY.

Global iteration requirements (see CONTRIBUTING.md) apply:

    Before committing and before marking the task complete,
    run `./scripts/check.sh` and confirm it exits with code 0.
    Paste the last 20 lines of its output in the final summary.
    The task is NOT complete until this is done. Do not mark
    the task done if the script reports any errors.

    unit + integration tests green,

    ruff check + ruff format clean,

    import-smoke green,

    e2e-smoke green (mandatory, no exceptions),

    README + docs/decisions.md updated,

    work ONLY in the current branch; do NOT create, rename, or
    delete branches; do NOT push to main.

Do NOT start Iteration <N+1>.
Stop after all required checks are green and post a summary.
```

---

## 1. Working Branch Model

- **Working Branch:** All development happens in a single long-lived working branch (e.g. `jules-3805668974257506057-99790dda` or active working branch). Auto-generated `jules-*` branch names are expected and fully acceptable.
- **Archival Snapshot Branches:** The human maintainer periodically snapshots successful milestone states into separate archival branches named `iteration-1`, `iteration-2`, `iteration-3`, etc. These archival branches are created, tagged, and managed ONLY by the human maintainer via the GitHub UI or local git. Jules never creates or touches them.
- **Iteration Bookkeeping:** Iteration numbering exists for the maintainer's bookkeeping and progress tracking. It does NOT require or imply separate git branches for the automated agent.
- **Minimal `main` Branch:** The `main` branch is intentionally kept minimal (containing foundational documentation like `docs/`). Jules never pushes to `main`.
- **No Branch Operations:** Jules never creates, renames, deletes, or switches branches on remote.

---

## 2. Explicit Rules for Automated Agents (Jules)

> **"Work ONLY in the current branch. Do not create, rename, or delete branches. Do not push to main. Push commits to the branch you were started on."**

---

## 3. Required CI Quality Checks

All commits pushed to the working branch must pass the following required CI checks in GitHub Actions:

- **`Run Import Smoke Check` (`import-smoke`)**: Installs base `requirements.txt` (including runtime `psycopg[binary]`) and executes `pytest tests/unit/test_import_smoke.py -x -q` to verify every module under `app/` imports cleanly without database connection requirements or reserved keyword syntax conflicts.
- **`Run Ruff Linter & Format Check` (`lint` / `format`)**: Executes `ruff check .` and `ruff format --check .`.
- **`Run Pytest Test Suite` (`tests`)**: Installs base `requirements.txt` and executes `pytest` with `--import-mode=importlib`.
- **`Run E2E Playwright Smoke Suite` (`e2e-smoke`)**: Installs `requirements.txt` and `requirements-e2e.txt` and executes `pytest -m e2e tests/e2e/ -x -q` against the running web application stack.

---

## 4. Optional Maintainer PR Branch-Name Policy

If Pull Requests are ever enabled by the maintainer in the repository settings:
- PR source branch names should match `^iteration-[0-9]+$` or `^iteration-[0-9]+-hotfix$`.
- Maintainers may bypass checks if needed using the `skip-branch-name-check` PR label.
- This policy is documented for maintainer reference.

# Contributing Guidelines & Working Branch Model

This repository follows a **single long-lived working-branch model** for development, with manual maintainer snapshotting for release bookkeeping.

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

- **`Run Import Smoke Check` (`import-smoke`)**: Executes `pytest tests/test_import_smoke.py -x -q` to verify every module under `app/` imports without error and no Python reserved keywords (like `import`) are used as package or module names.
- **`Run Ruff Linter & Format Check` (`lint` / `format`)**: Executes `ruff check .` and `ruff format --check .`.
- **`Run Pytest Test Suite` (`tests`)**: Executes `pytest` with `--import-mode=importlib`.
- **`Container Smoke Tests`**: Verifies E2E container startup and route health checks in Docker Compose.

---

## 4. Optional Maintainer PR Branch-Name Policy

If Pull Requests are ever enabled by the maintainer in the repository settings:
- PR source branch names should match `^iteration-[0-9]+$` or `^iteration-[0-9]+-hotfix$`.
- Maintainers may bypass checks if needed using the `skip-branch-name-check` PR label.
- This policy is documented for maintainer reference.

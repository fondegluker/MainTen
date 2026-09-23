# Contributing Guidelines & Branch Policy

This repository follows a strict **iteration-based branching policy**. All contributors and automated agents must adhere to the workflow below.

---

## 1. Branch Naming Policy

- **Iteration Branches:** Every numbered iteration $N$ ($N = 1, 2, 3, \dots$) must be developed on its own dedicated feature branch named **EXACTLY**:
  ```
  iteration-<N>
  ```
  *Examples:* `iteration-1`, `iteration-2`, `iteration-3`, `iteration-4`
- **Hotfix Branches:** Hotfixes to a shipped iteration must be developed on:
  ```
  iteration-<N>-hotfix
  ```
  *Examples:* `iteration-3-hotfix`
- **Format Requirements:** Branch names must be lowercase, numbers, and hyphens only (`^iteration-[0-9]+(-hotfix)?$`).
- **Forbidden Names:** Never use prefixes like `feat/`, `jules/`, `user/`, underscores (`iteration_3`), timestamps, or random hash IDs (`jules-12345-abc`).
- **Branch Lifetime:** One iteration = one branch = one Pull Request against the base branch (`main`). Never mix multiple iterations in a single branch or PR.
- **Reopening a Branch:** If an iteration PR needs revision, reuse the existing `iteration-<N>` branch name. Do NOT create `iteration-N-v2`.

---

## 2. Starting a New Iteration

When starting work on Iteration $N+1$:

1. Ensure the previous iteration ($N$) has been merged into `main`.
2. Update your local `main` branch:
   ```bash
   git checkout main
   git pull origin main
   ```
3. Create the new iteration branch from `main`:
   ```bash
   git checkout -b iteration-<N+1>
   ```
4. Implement the iteration deliverables exclusively on this branch.
5. Push commits and open a Pull Request titled:
   ```
   Iteration <N+1>: <short description of scope>
   ```
6. Ensure all required CI checks pass before merging:
   - `import-smoke` (`pytest tests/test_import_smoke.py -x -q`)
   - `branch-name-check` (verifies branch matches `^iteration-[0-9]+(-hotfix)?$`)
   - `lint` (`ruff check .` and `ruff format --check .`)
   - `tests` (`pytest`)
   - `container-smoke` (E2E Docker Compose container health tests)
7. Merge strategy: Use **Merge Commit** to preserve iteration history on `main`.
8. Delete the remote feature branch after merging. Do not reuse old branches.

---

## 3. Explicit Instructions for Automated Agents (Jules)

- For Iteration $N$, you MUST create and work on a NEW branch named `iteration-N` created from `main`.
- Push all commits to `iteration-N`.
- Open a Pull Request from `iteration-N` against `main`.
- Do NOT reuse any earlier branch, and NEVER push directly to `main`.

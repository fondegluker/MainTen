#!/usr/bin/env bash
set -euo pipefail

# Fall back gracefully to active virtualenv, PATH, or python module invocation
if [ -f "/app/venv/bin/ruff" ]; then
    RUFF_CMD="/app/venv/bin/ruff"
elif command -v ruff &> /dev/null; then
    RUFF_CMD="ruff"
else
    RUFF_CMD="python -m ruff"
fi

if [ -f "/app/venv/bin/pytest" ]; then
    PYTEST_CMD="/app/venv/bin/pytest"
elif command -v pytest &> /dev/null; then
    PYTEST_CMD="pytest"
else
    PYTEST_CMD="python -m pytest"
fi

$RUFF_CMD check . --fix
$RUFF_CMD format .
$RUFF_CMD check .
$RUFF_CMD format --check .
$PYTEST_CMD

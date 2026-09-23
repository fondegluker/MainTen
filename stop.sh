#!/usr/bin/env bash
set -euo pipefail
CLONE_DIR="${HOME}/MainTen"
cd "$CLONE_DIR"
if docker compose version >/dev/null 2>&1; then C="docker compose"; else C="docker-compose"; fi
$C down "$@"
echo "Остановлено. Флаг -v не передан — данные БД сохранены."
# Чтобы стереть БД:  bash stop.sh -v

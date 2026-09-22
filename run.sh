#!/usr/bin/env bash
# =============================================================================
# MainTen — локальный запуск через Docker для тестирования
# =============================================================================
set -euo pipefail

# ----------------------------- НАСТРОЙКИ ------------------------------------
REPO_URL="https://github.com/fondegluker/MainTen.git"
BRANCH="jules-3805668974257506057-99790dda"
CLONE_DIR="${HOME}/MainTen"              # куда клонировать
WEB_PORT="8000"                           # порт приложения на хосте
DB_PORT="5432"                            # порт Postgres на хосте (может конфликтовать)
# ---------------------------------------------------------------------------

# --- цвета для вывода -------------------------------------------------------
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERR ]${NC} $*" >&2; }

# --- проверка зависимостей --------------------------------------------------
need() { command -v "$1" >/dev/null 2>&1 || { error "Не найдено: $1. Установите и повторите."; exit 1; }; }
need git
need docker
if ! docker compose version >/dev/null 2>&1; then
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE="docker-compose"
  else
    error "Не найден 'docker compose' (v2) или 'docker-compose' (v1)."
    exit 1
  fi
else
  COMPOSE="docker compose"
fi
info "Используется: $COMPOSE"

# --- клонирование / обновление репозитория ----------------------------------
if [ ! -d "$CLONE_DIR/.git" ]; then
  info "Клонирую $REPO_URL в $CLONE_DIR"
  git clone "$REPO_URL" "$CLONE_DIR"
else
  info "Репозиторий уже есть: $CLONE_DIR"
fi

cd "$CLONE_DIR"

info "Получаю список веток с origin..."
git fetch --all --prune

info "Переключаюсь на ветку: $BRANCH"
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git checkout "$BRANCH"
else
  git checkout -b "$BRANCH" --track "origin/$BRANCH"
fi

info "Подтягиваю последние изменения (fast-forward)."
git pull --ff-only origin "$BRANCH" || {
  warn "git pull не удался (возможно, локальные изменения). Продолжаю как есть."
}

echo
info "Текущий коммит:"
git log -1 --oneline --decorate
echo

# --- проверка наличия docker-compose.yml ------------------------------------
if [ ! -f docker-compose.yml ] && [ ! -f compose.yml ]; then
  error "В $CLONE_DIR нет docker-compose.yml (или compose.yml)."
  exit 1
fi

# --- остановка прошлых контейнеров и очистка (опционально) ------------------
info "Останавливаю предыдущие контейнеры проекта (если есть)..."
$COMPOSE down --remove-orphans || true

# --- сборка и запуск --------------------------------------------------------
info "Собираю образы (--build). Первый запуск может занять несколько минут..."
$COMPOSE build

info "Поднимаю сервисы..."
$COMPOSE up -d

# --- ожидание готовности web ------------------------------------------------
info "Жду, пока web-сервис начнёт отвечать на http://localhost:${WEB_PORT} ..."
ATTEMPTS=60
for i in $(seq 1 "$ATTEMPTS"); do
  if curl -fsS -o /dev/null "http://localhost:${WEB_PORT}/" ; then
    info "Web-сервис отвечает."
    break
  fi
  sleep 2
  if [ "$i" -eq "$ATTEMPTS" ]; then
    warn "Web-сервис не ответил за $((ATTEMPTS*2)) секунд. Смотрите логи:"
    echo "    $COMPOSE logs -f web"
  fi
done

# --- статус -----------------------------------------------------------------
echo
info "Статус контейнеров:"
$COMPOSE ps

echo
info "Последние 30 строк логов web:"
$COMPOSE logs --tail=30 web || true

cat <<EOF

================================================================
✅ Готово.

Приложение:        http://localhost:${WEB_PORT}/
Postgres (host):   localhost:${DB_PORT}  (user=cfms_user / db=cfms_db)

Полезные команды (из каталога $CLONE_DIR):
  $COMPOSE logs -f web           # логи приложения
  $COMPOSE logs -f db            # логи Postgres
  $COMPOSE exec web bash         # шелл внутрь контейнера
  $COMPOSE exec db psql -U cfms_user -d cfms_db   # psql
  $COMPOSE restart web           # перезапуск web
  $COMPOSE down                  # остановить (данные Postgres сохранятся)
  $COMPOSE down -v               # остановить и СТЕРЕТЬ БД (volume)

Повторный запуск с обновлением кода:
  bash run.sh
================================================================
EOF

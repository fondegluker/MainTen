from fastapi import Request

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ru": {
        "app_title": "Система планирования ТО ПК",
        "login": "Вход в систему",
        "username_or_email": "Имя пользователя или Email",
        "password": "Пароль",
        "sign_in": "Войти",
        "logout": "Выйти",
        "admin_dashboard": "Панель администратора",
        "my_computers": "Мои компьютеры",
        "technician_schedule": "График техника",
        "reports": "Отчеты",
        "settings": "Настройки",
        "language": "Язык",
        "russian": "Русский",
        "english": "English",
        "welcome": "Добро пожаловать",
        "total_computers": "Всего компьютеров",
        "scheduled_events": "Запланировано ТО",
        "completed_events": "Выполнено ТО",
        "overdue_events": "Просрочено ТО",
        "invalid_credentials": "Неверное имя пользователя или пароль",
        "invalid_token": "Недействительная или просроченная ссылка доступа",
        "role_admin": "Администратор",
        "role_technician": "Техник",
        "role_user": "Пользователь",
        "role_observer": "Наблюдатель",
    },
    "en": {
        "app_title": "Computer Fleet Maintenance Scheduler",
        "login": "Sign In",
        "username_or_email": "Username or Email",
        "password": "Password",
        "sign_in": "Sign In",
        "logout": "Sign Out",
        "admin_dashboard": "Admin Dashboard",
        "my_computers": "My Computers",
        "technician_schedule": "Technician Schedule",
        "reports": "Reports",
        "settings": "Settings",
        "language": "Language",
        "russian": "Русский",
        "english": "English",
        "welcome": "Welcome",
        "total_computers": "Total Computers",
        "scheduled_events": "Scheduled Maintenance",
        "completed_events": "Completed Maintenance",
        "overdue_events": "Overdue Maintenance",
        "invalid_credentials": "Invalid username or password",
        "invalid_token": "Invalid or expired access token link",
        "role_admin": "Administrator",
        "role_technician": "Technician",
        "role_user": "User",
        "role_observer": "Observer",
    }
}

def get_locale(request: Request | None = None, user_locale: str | None = None) -> str:
    if user_locale in ("ru", "en"):
        return user_locale
    if request:
        cookie_locale = request.cookies.get("locale")
        if cookie_locale in ("ru", "en"):
            return cookie_locale
        accept_lang = request.headers.get("Accept-Language", "")
        if "en" in accept_lang.lower() and "ru" not in accept_lang.lower():
            return "en"
    return "ru"

def translate(key: str, locale: str = "ru") -> str:
    lang_dict = TRANSLATIONS.get(locale, TRANSLATIONS["ru"])
    return lang_dict.get(key, TRANSLATIONS["ru"].get(key, key))

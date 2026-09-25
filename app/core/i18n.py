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
        "users_management": "Пользователи",
        "computers_management": "Компьютеры",
        "technicians_management": "Техники",
        "import_fleet": "Импорт из Excel",
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
        "add_user": "Добавить пользователя",
        "edit_user": "Редактировать пользователя",
        "username": "Имя пользователя",
        "email_or_login": "Email / Логин",
        "role": "Роль",
        "status": "Статус",
        "active": "Активен",
        "inactive": "Неактивен",
        "actions": "Действия",
        "edit": "Изменить",
        "delete": "Удалить",
        "save": "Сохранить",
        "cancel": "Отмена",
        "add_computer": "Добавить компьютер",
        "edit_computer": "Редактировать компьютер",
        "hostname": "Имя хоста",
        "ip_address": "IP-адрес",
        "mac_address": "MAC-адрес",
        "os": "Операционная система",
        "location": "Кабинет / Расположение",
        "owner": "Владелец / Пользователь",
        "is_round_the_clock": "Круглосуточный ПК (24/7)",
        "notes": "Заметки",
        "unassigned": "Не назначен",
        "yes": "Да",
        "no": "Нет",
        "preview_import": "Предпросмотр импорта",
        "confirm_import": "Подтвердить импорт",
        "import_success": "Импорт успешно завершен",
        "last_maintenance": "Дата последнего обслуживания",
        "select_maintenance_date": "Выберите дату технического обслуживания (ТО)",
        "due_by": "Срок до",
        "chosen_maintenance_date": "Выбранная дата технического обслуживания:",
        "change_date": "Изменить дату",
        "select_new_date": "Выберите новую дату обслуживания:",
        "save_new_date": "Сохранить новую дату",
        "select_this_date": "Выбрать эту дату",
        "available_working_day": "Свободный рабочий день",
        "no_available_dates": "К сожалению, нет доступных свободных рабочих дней в окне выбора. Обратитесь к администратору.",
        "window_opens_on": "Окно выбора откроется",
        "my_computer_info": "Информация о моём компьютере",
        "today": "Сегодня",
    },
    "en": {
        "app_title": "Computer Fleet Maintenance Scheduler",
        "login": "Sign In",
        "username_or_email": "Username or Email",
        "password": "Password",
        "sign_in": "Sign In",
        "logout": "Sign Out",
        "admin_dashboard": "Admin Dashboard",
        "users_management": "Users",
        "computers_management": "Computers",
        "technicians_management": "Technicians",
        "import_fleet": "Excel Import",
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
        "add_user": "Add User",
        "edit_user": "Edit User",
        "username": "Username",
        "email_or_login": "Email / Login",
        "role": "Role",
        "status": "Status",
        "active": "Active",
        "inactive": "Inactive",
        "actions": "Actions",
        "edit": "Edit",
        "delete": "Delete",
        "save": "Save",
        "cancel": "Cancel",
        "add_computer": "Add Computer",
        "edit_computer": "Edit Computer",
        "hostname": "Hostname",
        "ip_address": "IP Address",
        "mac_address": "MAC Address",
        "os": "Operating System",
        "location": "Location / Room",
        "owner": "Owner / User",
        "is_round_the_clock": "Round the Clock (24/7)",
        "notes": "Notes",
        "unassigned": "Unassigned",
        "yes": "Yes",
        "no": "No",
        "preview_import": "Preview Import",
        "confirm_import": "Confirm Import",
        "import_success": "Import completed successfully",
        "last_maintenance": "Last maintenance",
        "select_maintenance_date": "Select maintenance date",
        "due_by": "Due by",
        "chosen_maintenance_date": "Scheduled maintenance date:",
        "change_date": "Change Date",
        "select_new_date": "Select a new maintenance date:",
        "save_new_date": "Save New Date",
        "select_this_date": "Select This Date",
        "available_working_day": "Available working day",
        "no_available_dates": "No available working dates in the selection window. Please contact an administrator.",
        "window_opens_on": "Selection window will open on",
        "my_computer_info": "My Computer Details",
        "today": "Today",
    },
}

from datetime import date

WEEK_LAYOUT = [["mon", "tue", "wed"], ["thu", "fri", "sat"]]

WEEKDAYS_6_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]
WEEKDAYS_6_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
WEEKDAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

MONTHS_RU = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]
MONTHS_EN = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def format_date_localized(d: date | str, locale: str = "ru", include_weekday: bool = True) -> str:
    """Format date localized according to app locale (ru or en)."""
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d.strip())
        except ValueError:
            return d

    if not isinstance(d, date):
        return str(d)

    date_str = d.strftime("%d.%m.%Y")
    if not include_weekday:
        return date_str

    w_idx = d.weekday()  # 0 = Monday, 6 = Sunday
    w_names = WEEKDAYS_EN if locale == "en" else WEEKDAYS_RU
    return f"{date_str} ({w_names[w_idx]})"


def get_locale(request: Request | None = None, user_locale: str | None = None) -> str:
    # 1. Explicit query parameter ?lang= or ?locale=
    if request:
        lang_param = request.query_params.get("lang") or request.query_params.get("locale")
        if lang_param in ("ru", "en"):
            return lang_param

    # 2. Authenticated user DB locale
    if user_locale in ("ru", "en"):
        return user_locale

    # 3. Cookie locale
    if request:
        cookie_locale = request.cookies.get("locale")
        if cookie_locale in ("ru", "en"):
            return cookie_locale

    # 4. Default ru
    return "ru"


def translate(key: str, locale: str = "ru") -> str:
    lang_dict = TRANSLATIONS.get(locale, TRANSLATIONS["ru"])
    return lang_dict.get(key, TRANSLATIONS["ru"].get(key, key))

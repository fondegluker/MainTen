"""Configuration export and import service for CFMS (§1)."""

import io
import json
import zipfile
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import (
    Computer,
    DayKind,
    MaintenanceProtocolItem,
    Setting,
    User,
    UserRole,
    WorkingCalendar,
)
from app.services.audit_service import log_audit
from app.services.crypto_service import decrypt_bytes, encrypt_bytes

SCHEMA_VERSION = 1
APP_VERSION = "1.0.0"


def export_configuration(db: Session, password: str | None = None) -> tuple[bytes, str]:
    """Export configuration reference data to ZIP bytes and filename.
    If password is provided, payload is encrypted to configuration.json.enc.
    """
    settings_rows = db.query(Setting).all()
    settings_data = {s.key: s.value_json for s in settings_rows}

    protocol_items = db.query(MaintenanceProtocolItem).all()
    protocol_data = [
        {
            "id": p.id,
            "order_index": p.order_index,
            "title_ru": p.title_ru,
            "title_en": p.title_en,
            "description": p.description,
            "is_active": p.is_active,
        }
        for p in protocol_items
    ]

    calendar_rows = db.query(WorkingCalendar).all()
    calendar_data = [
        {
            "date": c.date.isoformat() if isinstance(c.date, date) else str(c.date),
            "is_working": c.is_working,
            "kind": c.kind.value if hasattr(c.kind, "value") else str(c.kind),
            "description": c.description,
            "source": getattr(c, "source", "seed"),
        }
        for c in calendar_rows
    ]

    computers = db.query(Computer).all()
    computers_data = [
        {
            "hostname": c.hostname,
            "ip": c.ip,
            "mac": c.mac,
            "os": c.os,
            "location": c.location,
            "owner_username": c.owner_user.username if c.owner_user else None,
            "is_round_the_clock": c.is_round_the_clock,
            "last_maintenance_at": c.last_maintenance_at.isoformat() if c.last_maintenance_at else None,
            "next_maintenance_due_at": c.next_maintenance_due_at.isoformat() if c.next_maintenance_due_at else None,
            "status": c.status,
            "notes": c.notes,
        }
        for c in computers
    ]

    users = db.query(User).all()
    users_data = [
        {
            "username": u.username,
            "email_or_login": u.email_or_login,
            "password_hash": u.password_hash,
            "role": u.role.value if hasattr(u.role, "value") else str(u.role),
            "locale": u.locale,
            "is_active": u.is_active,
        }
        for u in users
    ]

    config_payload = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "app_version": APP_VERSION,
        "settings": settings_data,
        "protocol_items": protocol_data,
        "working_calendar": calendar_data,
        "computers": computers_data,
        "users": users_data,
    }

    json_bytes = json.dumps(config_payload, ensure_ascii=False, indent=2).encode("utf-8")

    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    buf = io.BytesIO()

    if password and password.strip():
        enc_payload = encrypt_bytes(json_bytes, password.strip())
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("configuration.json.enc", enc_payload)
        filename = f"mainten-config-{ts_str}.zip.enc"
    else:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("configuration.json", json_bytes)
        filename = f"mainten-config-{ts_str}.zip"

    buf.seek(0)
    return buf.getvalue(), filename


def parse_and_preview_configuration(
    zip_bytes: bytes, password: str | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse configuration zip archive, decrypt if needed, validate structure, and return (preview_data, raw_payload)."""
    try:
        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, "r") as zf:
            file_names = zf.namelist()

            if "configuration.json.enc" in file_names:
                if not password or not password.strip():
                    raise ValueError("Пароль обязателен для зашифрованного архива конфигурации")
                enc_data = zf.read("configuration.json.enc")
                json_bytes = decrypt_bytes(enc_data, password.strip())
            elif "configuration.json" in file_names:
                json_bytes = zf.read("configuration.json")
            else:
                raise ValueError("Архив не содержит файл конфигурации (configuration.json)")
    except zipfile.BadZipFile:
        raise ValueError("Загруженный файл не является корректным ZIP-архивом")

    try:
        payload = json.loads(json_bytes.decode("utf-8"))
    except Exception:
        raise ValueError("Некорректный формат JSON внутри файла конфигурации")

    if not isinstance(payload, dict):
        raise ValueError("Содержимое конфигурации должно быть JSON-объектом")

    schema_ver = payload.get("schema_version")
    if schema_ver != SCHEMA_VERSION:
        raise ValueError(f"Неподдерживаемая версия схемы конфигурации: {schema_ver}. Ожидалась версия {SCHEMA_VERSION}.")

    users = payload.get("users", [])
    computers = payload.get("computers", [])
    calendar_rows = payload.get("working_calendar", [])
    protocol_items = payload.get("protocol_items", [])
    settings_dict = payload.get("settings", {})

    preview = {
        "users_count": len(users),
        "computers_count": len(computers),
        "calendar_count": len(calendar_rows),
        "protocol_count": len(protocol_items),
        "settings_count": len(settings_dict),
        "is_encrypted": "configuration.json.enc" in file_names,
    }

    return preview, payload


def confirm_import_configuration(
    payload: dict[str, Any], actor_user_id: int, filename: str, is_encrypted: bool, db: Session
) -> dict[str, Any]:
    """Apply configuration payload in a single atomic database transaction."""
    settings_dict = payload.get("settings", {})
    protocol_items = payload.get("protocol_items", [])
    calendar_rows = payload.get("working_calendar", [])
    computers = payload.get("computers", [])
    users = payload.get("users", [])

    counts = {"settings": 0, "users": 0, "computers": 0, "calendar": 0, "protocol": 0}

    # 1. Upsert Settings
    for key, val in settings_dict.items():
        s = db.query(Setting).filter(Setting.key == key).first()
        if s:
            s.value_json = val
        else:
            s = Setting(key=key, value_json=val)
            db.add(s)
        counts["settings"] += 1

    # 2. Upsert Users by username
    user_map = {}
    for u_data in users:
        username = u_data.get("username")
        if not username:
            continue
        role_str = str(u_data.get("role", "user")).lower()
        role_enum = UserRole(role_str) if role_str in UserRole._value2member_map_ else UserRole.USER

        u = db.query(User).filter(User.username == username).first()
        if u:
            u.email_or_login = u_data.get("email_or_login", u.email_or_login)
            if u_data.get("password_hash"):
                u.password_hash = u_data.get("password_hash")
            u.role = role_enum
            u.locale = u_data.get("locale", "ru")
            u.is_active = u_data.get("is_active", True)
        else:
            u = User(
                username=username,
                email_or_login=u_data.get("email_or_login", username),
                password_hash=u_data.get("password_hash", ""),
                role=role_enum,
                locale=u_data.get("locale", "ru"),
                is_active=u_data.get("is_active", True),
                created_at=datetime.now(timezone.utc),
            )
            db.add(u)
        db.flush()
        user_map[username] = u.id
        counts["users"] += 1

    # 3. Upsert Protocol Items by title_ru / order_index
    for p_data in protocol_items:
        title_ru = p_data.get("title_ru")
        order_idx = p_data.get("order_index", 1)

        p = db.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.title_ru == title_ru).first()
        if not p:
            p = db.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.order_index == order_idx).first()

        if p:
            p.title_ru = title_ru or p.title_ru
            p.title_en = p_data.get("title_en", p.title_en)
            p.description = p_data.get("description", p.description)
            p.order_index = order_idx
            p.is_active = p_data.get("is_active", True)
            p.updated_at = datetime.now(timezone.utc)
        else:
            p = MaintenanceProtocolItem(
                order_index=order_idx,
                title_ru=title_ru or f"Пункт {order_idx}",
                title_en=p_data.get("title_en"),
                description=p_data.get("description"),
                is_active=p_data.get("is_active", True),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(p)
        counts["protocol"] += 1

    # 4. Upsert Working Calendar by date
    for c_data in calendar_rows:
        d_str = c_data.get("date")
        if not d_str:
            continue
        c_date = date.fromisoformat(d_str)
        kind_str = str(c_data.get("kind", "workday")).lower()
        kind_enum = DayKind(kind_str) if kind_str in DayKind._value2member_map_ else DayKind.WORKDAY

        cal = db.query(WorkingCalendar).filter(WorkingCalendar.date == c_date).first()
        if cal:
            cal.is_working = c_data.get("is_working", True)
            cal.kind = kind_enum
            cal.description = c_data.get("description")
            if "source" in c_data:
                cal.source = c_data.get("source")
        else:
            cal = WorkingCalendar(
                date=c_date,
                is_working=c_data.get("is_working", True),
                kind=kind_enum,
                description=c_data.get("description"),
                source=c_data.get("source", "import"),
            )
            db.add(cal)
        counts["calendar"] += 1

    # 5. Upsert Computers by hostname
    for comp_data in computers:
        hostname = comp_data.get("hostname")
        if not hostname:
            continue

        owner_user_id = None
        owner_username = comp_data.get("owner_username")
        if owner_username and owner_username in user_map:
            owner_user_id = user_map[owner_username]

        last_maint = (
            datetime.fromisoformat(comp_data["last_maintenance_at"]) if comp_data.get("last_maintenance_at") else None
        )
        next_due = (
            datetime.fromisoformat(comp_data["next_maintenance_due_at"])
            if comp_data.get("next_maintenance_due_at")
            else None
        )

        c = db.query(Computer).filter(Computer.hostname == hostname).first()
        if c:
            c.ip = comp_data.get("ip", c.ip)
            c.mac = comp_data.get("mac", c.mac)
            c.os = comp_data.get("os", c.os)
            c.location = comp_data.get("location", c.location)
            if owner_user_id:
                c.owner_user_id = owner_user_id
            c.is_round_the_clock = comp_data.get("is_round_the_clock", c.is_round_the_clock)
            if last_maint:
                c.last_maintenance_at = last_maint
            if next_due:
                c.next_maintenance_due_at = next_due
            c.status = comp_data.get("status", c.status)
            c.notes = comp_data.get("notes", c.notes)
        else:
            c = Computer(
                hostname=hostname,
                ip=comp_data.get("ip"),
                mac=comp_data.get("mac"),
                os=comp_data.get("os"),
                location=comp_data.get("location"),
                owner_user_id=owner_user_id,
                is_round_the_clock=comp_data.get("is_round_the_clock", False),
                last_maintenance_at=last_maint,
                next_maintenance_due_at=next_due,
                status=comp_data.get("status", "active"),
                notes=comp_data.get("notes"),
                created_at=datetime.now(timezone.utc),
            )
            db.add(c)
        counts["computers"] += 1

    log_audit(
        db=db,
        actor_user_id=actor_user_id,
        action="import_configuration",
        entity="settings",
        entity_id=None,
        after={
            "source_filename": filename,
            "is_encrypted": is_encrypted,
            "counts": counts,
        },
    )
    db.commit()

    return counts

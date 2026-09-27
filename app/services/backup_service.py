"""Database and uploads backup and restore service for CFMS (§2)."""

import io
import json
import os
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.audit_service import log_audit
from app.services.crypto_service import decrypt_bytes, encrypt_bytes, is_encrypted_envelope

SCHEMA_VERSION = 1
APP_VERSION = "1.0.0"
UPLOADS_DIR = "/app/uploads"


def _generate_sql_dump(db: Session) -> str:
    """Generate SQL dump using pg_dump if postgresql URL, or SQL dump fallback."""
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql"):
        try:
            cmd = [
                "pg_dump",
                "--no-owner",
                "--no-privileges",
                "--clean",
                "--if-exists",
                db_url,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return proc.stdout
        except Exception:
            pass

    # Fallback SQL export for SQLite or when pg_dump is unavailable
    sql_lines = [
        "BEGIN TRANSACTION;",
    ]
    for table_name in [
        "settings",
        "users",
        "working_calendar",
        "computers",
        "maintenance_protocol_items",
        "maintenance_events",
        "maintenance_event_checks",
        "maintenance_event_attachments",
        "notifications",
        "audit_log",
    ]:
        try:
            result = db.execute(text(f"SELECT * FROM {table_name}")).fetchall()
            for row in result:
                vals = [f"'{str(v).replace('\'', '\'\'')}'" if v is not None else "NULL" for v in row]
                val_str = ", ".join(vals)
                sql_lines.append(f"INSERT INTO {table_name} VALUES ({val_str});")
        except Exception:
            pass
    sql_lines.append("COMMIT;")
    return "\n".join(sql_lines)


def export_backup(db: Session, password: str | None = None) -> tuple[bytes, str]:
    """Generate full database + attachments backup ZIP archive (or encrypted .zip.enc)."""
    sql_content = _generate_sql_dump(db)

    upload_files = []
    if os.path.exists(UPLOADS_DIR):
        for root, _, files in os.walk(UPLOADS_DIR):
            for f in files:
                abs_path = os.path.join(root, f)
                rel_path = os.path.relpath(abs_path, UPLOADS_DIR)
                upload_files.append((abs_path, os.path.join("uploads", rel_path)))

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "app_version": APP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "pg_dump_format": "plain",
        "file_count": len(upload_files) + 2,
        "uploads_file_count": len(upload_files),
    }

    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    sql_bytes = sql_content.encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_bytes)
        zf.writestr("database.sql", sql_bytes)
        for abs_p, zip_p in upload_files:
            if os.path.exists(abs_p):
                with open(abs_p, "rb") as fp:
                    zf.writestr(zip_p, fp.read())

    raw_zip_bytes = buf.getvalue()
    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    if password and password.strip():
        enc_zip_bytes = encrypt_bytes(raw_zip_bytes, password.strip())
        filename = f"mainten-backup-{ts_str}.zip.enc"
        return enc_zip_bytes, filename
    else:
        filename = f"mainten-backup-{ts_str}.zip"
        return raw_zip_bytes, filename


def parse_and_preview_backup(
    archive_bytes: bytes, password: str | None = None
) -> tuple[dict[str, Any], bytes]:
    """Parse backup archive (decrypting if encrypted) and return (preview_metadata, plain_zip_bytes)."""
    is_enc = is_encrypted_envelope(archive_bytes)
    if is_enc:
        if not password or not password.strip():
            raise ValueError("Пароль обязателен для зашифрованного архива резервной копии")
        plain_zip_bytes = decrypt_bytes(archive_bytes, password.strip())
    else:
        plain_zip_bytes = archive_bytes

    try:
        buf = io.BytesIO(plain_zip_bytes)
        with zipfile.ZipFile(buf, "r") as zf:
            file_names = zf.namelist()
            if "manifest.json" not in file_names or "database.sql" not in file_names:
                raise ValueError("Архив не содержит обязательные файлы manifest.json и database.sql")

            manifest_bytes = zf.read("manifest.json")
            manifest = json.loads(manifest_bytes.decode("utf-8"))

            uploads_files = [fn for fn in file_names if fn.startswith("uploads/")]
            total_uploads_size = sum(zf.getinfo(fn).file_size for fn in uploads_files)

            sql_size = zf.getinfo("database.sql").file_size

            preview = {
                "manifest": manifest,
                "sql_size_bytes": sql_size,
                "uploads_count": len(uploads_files),
                "uploads_size_bytes": total_uploads_size,
                "is_encrypted": is_enc,
            }
            return preview, plain_zip_bytes
    except zipfile.BadZipFile:
        raise ValueError("Загруженный файл не является корректным ZIP-архивом (неверный пароль или повреждённый файл)")


def confirm_restore_backup(
    plain_zip_bytes: bytes, confirmation_text: str, actor_user_id: int, filename: str, is_encrypted: bool, db: Session
) -> dict[str, Any]:
    """Restore database and attachments from backup ZIP archive."""
    normalized_confirm = confirmation_text.strip().upper() if confirmation_text else ""
    if normalized_confirm not in ("RESTORE", "ВОССТАНОВИТЬ"):
        raise ValueError("Для подтверждения восстановления введите слово RESTORE")

    buf = io.BytesIO(plain_zip_bytes)
    with zipfile.ZipFile(buf, "r") as zf:
        sql_bytes = zf.read("database.sql")
        sql_content = sql_bytes.decode("utf-8")

        # 1. Execute SQL dump against database
        db_url = settings.DATABASE_URL
        restored_via_psql = False
        if db_url.startswith("postgresql") and shutil.which("psql"):
            try:
                cmd = ["psql", db_url]
                subprocess.run(cmd, input=sql_content, capture_output=True, text=True, check=True)
                restored_via_psql = True
            except Exception:
                pass

        if not restored_via_psql:
            # Direct DBAPI raw_connection execution to avoid SQLAlchemy text() colon parameter parsing issues
            try:
                raw_conn = db.bind.raw_connection()
                cursor = raw_conn.cursor()
                cursor.execute(sql_content)
                raw_conn.commit()
                cursor.close()
                raw_conn.close()
            except Exception:
                for statement in sql_content.split(";"):
                    stmt = statement.strip()
                    if stmt:
                        try:
                            db.execute(text(stmt.replace(":", "\\:")))
                        except Exception:
                            pass
                db.commit()

        # 2. Replace uploads directory
        if os.path.exists(UPLOADS_DIR):
            try:
                shutil.rmtree(UPLOADS_DIR)
            except Exception:
                pass
        os.makedirs(UPLOADS_DIR, exist_ok=True)

        uploads_files = [fn for fn in zf.namelist() if fn.startswith("uploads/") and not fn.endswith("/")]
        for zip_fn in uploads_files:
            rel_path = os.path.relpath(zip_fn, "uploads")
            dest_path = os.path.join(UPLOADS_DIR, rel_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, "wb") as f_out:
                f_out.write(zf.read(zip_fn))

    log_audit(
        db=db,
        actor_user_id=actor_user_id,
        action="restore_backup",
        entity="database",
        entity_id=None,
        after={
            "source_filename": filename,
            "is_encrypted": is_encrypted,
            "uploads_restored": len(uploads_files),
        },
    )
    db.commit()

    return {"status": "success", "uploads_restored": len(uploads_files)}

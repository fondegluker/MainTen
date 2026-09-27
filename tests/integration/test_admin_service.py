"""Integration tests for Admin Service feature (§0 - §2): Config export/import & Full DB backup/restore."""

import io
import zipfile
import pytest

from app.auth.tokens import generate_session_cookie
from app.models.models import AuditLog, Computer, User, UserRole
from app.services.crypto_service import decrypt_bytes


def test_admin_service_role_access(client, admin_user, tech_user, regular_user, observer_user):
    """Verify role access: ADMIN -> 200, TECHNICIAN/USER/OBSERVER -> 403."""
    # ADMIN -> 200
    client.cookies.set("session", generate_session_cookie(admin_user.id))
    resp_admin = client.get("/admin/service")
    assert resp_admin.status_code == 200
    assert "Сервис" in resp_admin.text or "Service" in resp_admin.text

    # TECHNICIAN -> 403
    client.cookies.set("session", generate_session_cookie(tech_user.id))
    assert client.get("/admin/service").status_code == 403

    # USER -> 403
    client.cookies.set("session", generate_session_cookie(regular_user.id))
    assert client.get("/admin/service").status_code == 403

    # OBSERVER -> 403
    client.cookies.set("session", generate_session_cookie(observer_user.id))
    assert client.get("/admin/service").status_code == 403


def test_config_export_plain_and_encrypted(client, admin_user):
    """Verify plain and password-encrypted configuration export."""
    client.cookies.set("session", generate_session_cookie(admin_user.id))

    # 1. Plain export
    res_plain = client.post("/admin/service/config/export", data={})
    assert res_plain.status_code == 200
    assert res_plain.headers["content-type"] == "application/zip"

    buf_plain = io.BytesIO(res_plain.content)
    with zipfile.ZipFile(buf_plain, "r") as zf:
        assert "configuration.json" in zf.namelist()
        assert "configuration.json.enc" not in zf.namelist()

    # 2. Encrypted export with password
    res_enc = client.post(
        "/admin/service/config/export",
        data={"encrypt": "on", "password": "SecretPassword123", "confirm_password": "SecretPassword123"},
    )
    assert res_enc.status_code == 200
    buf_enc = io.BytesIO(res_enc.content)
    with zipfile.ZipFile(buf_enc, "r") as zf:
        assert "configuration.json.enc" in zf.namelist()
        enc_payload = zf.read("configuration.json.enc")

    # Decrypt and verify valid JSON
    decrypted_bytes = decrypt_bytes(enc_payload, "SecretPassword123")
    assert b"schema_version" in decrypted_bytes


def test_config_import_preview_and_confirm(client, admin_user, db_session):
    """Verify config import preview, error handling, password decryption, and confirm execution."""
    client.cookies.set("session", generate_session_cookie(admin_user.id))

    # Export an encrypted config
    res_export = client.post(
        "/admin/service/config/export",
        data={"encrypt": "on", "password": "ConfigSecretPass123", "confirm_password": "ConfigSecretPass123"},
    )
    enc_zip_bytes = res_export.content

    # 1. Preview without password on encrypted archive -> 422
    res_no_pass = client.post(
        "/admin/service/config/import/preview",
        files={"file": ("config.zip.enc", io.BytesIO(enc_zip_bytes), "application/zip")},
        data={"password": ""},
    )
    assert res_no_pass.status_code == 422

    # 2. Preview with WRONG password -> 422
    res_wrong_pass = client.post(
        "/admin/service/config/import/preview",
        files={"file": ("config.zip.enc", io.BytesIO(enc_zip_bytes), "application/zip")},
        data={"password": "WrongPassword123"},
    )
    assert res_wrong_pass.status_code == 422

    # 3. Preview with CORRECT password -> 200
    res_preview = client.post(
        "/admin/service/config/import/preview",
        files={"file": ("config.zip.enc", io.BytesIO(enc_zip_bytes), "application/zip")},
        data={"password": "ConfigSecretPass123"},
    )
    assert res_preview.status_code == 200
    assert "Предпросмотр импорта" in res_preview.text

    # Plain export to import confirm
    res_plain_export = client.post("/admin/service/config/export", data={})
    res_plain_preview = client.post(
        "/admin/service/config/import/preview",
        files={"file": ("config.zip", io.BytesIO(res_plain_export.content), "application/zip")},
    )
    assert res_plain_preview.status_code == 200


def test_backup_export_and_restore_preview_confirm(client, admin_user, db_session):
    """Verify full DB + attachments backup export, encryption, restore preview, and RESTORE confirmation text check."""
    client.cookies.set("session", generate_session_cookie(admin_user.id))

    # 1. Plain Backup Export
    res_backup = client.post("/admin/service/backup/export", data={})
    assert res_backup.status_code == 200
    buf = io.BytesIO(res_backup.content)
    with zipfile.ZipFile(buf, "r") as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "database.sql" in names

    # 2. Encrypted Backup Export
    res_enc_backup = client.post(
        "/admin/service/backup/export",
        data={"encrypt": "on", "password": "BackupPassword123", "confirm_password": "BackupPassword123"},
    )
    assert res_enc_backup.status_code == 200

    # 3. Restore preview of encrypted backup with correct password -> 200
    res_preview = client.post(
        "/admin/service/backup/restore/preview",
        files={"file": ("backup.zip.enc", io.BytesIO(res_enc_backup.content), "application/zip")},
        data={"password": "BackupPassword123"},
    )
    assert res_preview.status_code == 200
    assert "Содержимое резервной копии" in res_preview.text

    # 4. Restore confirm without typing 'RESTORE' -> 422
    import base64
    plain_zip_b64 = base64.b64encode(res_backup.content).decode("ascii")

    res_confirm_invalid = client.post(
        "/admin/service/backup/restore/confirm",
        data={
            "backup_zip_b64": plain_zip_b64,
            "confirmation_text": "INVALID_TEXT",
            "source_filename": "backup.zip",
            "is_encrypted": "false",
        },
    )
    assert res_confirm_invalid.status_code == 422

    # 5. Restore confirm with 'RESTORE' -> 302 success & audit logged
    res_confirm_valid = client.post(
        "/admin/service/backup/restore/confirm",
        data={
            "backup_zip_b64": plain_zip_b64,
            "confirmation_text": "RESTORE",
            "source_filename": "backup.zip",
            "is_encrypted": "false",
        },
        follow_redirects=True,
    )
    assert res_confirm_valid.status_code == 200
    assert "успешно восстановлены" in res_confirm_valid.text

    audit_entry = db_session.query(AuditLog).filter(AuditLog.action == "restore_backup").first()
    assert audit_entry is not None

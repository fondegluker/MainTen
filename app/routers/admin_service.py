"""Admin Service router for Configuration Export/Import and Full Database Backup/Restore (§0 - §2)."""

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.core.database import get_db
from app.models.models import User
from app.routers.web import context_with_defaults
from app.services.backup_service import confirm_restore_backup, export_backup, parse_and_preview_backup
from app.services.config_service import (
    confirm_import_configuration,
    export_configuration,
    parse_and_preview_configuration,
)

router = APIRouter(prefix="/admin/service", tags=["admin_service"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def admin_service_page(
    request: Request,
    active_tab: str = "config",
    message: str | None = None,
    error: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Render Admin Service page with Configuration and Backup sections/tabs."""
    return templates.TemplateResponse(
        "admin/service.html",
        context_with_defaults(
            request,
            current_user,
            {
                "active_tab": active_tab,
                "message": message,
                "error": error,
            },
        ),
    )


@router.get("/config/export")
def config_export_get(
    request: Request,
    current_user: User = Depends(require_admin),
):
    """Redirect GET config export to main service page."""
    return RedirectResponse(url="/admin/service?active_tab=config", status_code=status.HTTP_302_FOUND)


@router.post("/config/export")
def config_export_post(
    request: Request,
    encrypt: str | None = Form(None),
    password: str | None = Form(None),
    confirm_password: str | None = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Export configuration ZIP archive with optional password encryption."""
    if encrypt and encrypt.lower() in ("1", "true", "on", "yes"):
        pass_str = password.strip() if password else ""
        confirm_pass_str = confirm_password.strip() if confirm_password else ""
        if not pass_str or len(pass_str) < 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Пароль должен содержать не менее 8 символов",
            )
        if pass_str != confirm_pass_str:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Пароли не совпадают",
            )
    else:
        pass_str = None

    zip_bytes, filename = export_configuration(db, password=pass_str)

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post("/config/import/preview")
async def config_import_preview(
    request: Request,
    file: UploadFile = File(...),
    password: str | None = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Parse configuration ZIP archive and return preview summary."""
    zip_bytes = await file.read()
    try:
        preview_data, payload = parse_and_preview_configuration(zip_bytes, password=password)
        return templates.TemplateResponse(
            "admin/service.html",
            context_with_defaults(
                request,
                current_user,
                {
                    "active_tab": "config",
                    "config_preview": preview_data,
                    "config_payload_json": json.dumps(payload, ensure_ascii=False),
                    "source_filename": file.filename,
                    "is_encrypted": preview_data["is_encrypted"],
                    "message": "Файл конфигурации проверен. Подтвердите импорт.",
                },
            ),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )


@router.post("/config/import/confirm")
def config_import_confirm(
    request: Request,
    payload_json: str = Form(...),
    source_filename: str = Form("config.zip"),
    is_encrypted: str = Form("false"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Confirm and apply configuration import payload."""
    try:
        payload = json.loads(payload_json)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Некорректный JSON payload конфигурации",
        )

    enc_flag = str(is_encrypted).lower() in ("true", "1", "yes", "on")
    counts = confirm_import_configuration(
        payload=payload,
        actor_user_id=current_user.id,
        filename=source_filename,
        is_encrypted=enc_flag,
        db=db,
    )

    msg = f"Конфигурация успешно импортирована (ПК: {counts['computers']}, Пользователи: {counts['users']}, Регламент: {counts['protocol']})."
    return RedirectResponse(
        url=f"/admin/service?active_tab=config&message={msg}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/backup")
def backup_get(
    request: Request,
    current_user: User = Depends(require_admin),
):
    """Redirect GET backup to main service page with backup tab active."""
    return RedirectResponse(url="/admin/service?active_tab=backup", status_code=status.HTTP_302_FOUND)


@router.post("/backup/export")
def backup_export_post(
    request: Request,
    encrypt: str | None = Form(None),
    password: str | None = Form(None),
    confirm_password: str | None = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Export full database + attachments backup archive."""
    if encrypt and encrypt.lower() in ("1", "true", "on", "yes"):
        pass_str = password.strip() if password else ""
        confirm_pass_str = confirm_password.strip() if confirm_password else ""
        if not pass_str or len(pass_str) < 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Пароль должен содержать не менее 8 символов",
            )
        if pass_str != confirm_pass_str:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Пароли не совпадают",
            )
    else:
        pass_str = None

    archive_bytes, filename = export_backup(db, password=pass_str)

    return Response(
        content=archive_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post("/backup/restore/preview")
async def backup_restore_preview(
    request: Request,
    file: UploadFile = File(...),
    password: str | None = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Parse backup archive and return restore preview."""
    archive_bytes = await file.read()
    try:
        preview_data, plain_zip_bytes = parse_and_preview_backup(archive_bytes, password=password)
        import base64

        plain_b64 = base64.b64encode(plain_zip_bytes).decode("ascii")

        return templates.TemplateResponse(
            "admin/service.html",
            context_with_defaults(
                request,
                current_user,
                {
                    "active_tab": "backup",
                    "backup_preview": preview_data,
                    "backup_zip_b64": plain_b64,
                    "source_filename": file.filename,
                    "is_encrypted": preview_data["is_encrypted"],
                    "message": "Архив резервной копии проверен. Введите RESTORE для подтверждения.",
                },
            ),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )


@router.post("/backup/restore/confirm")
def backup_restore_confirm(
    request: Request,
    backup_zip_b64: str = Form(...),
    confirmation_text: str = Form(...),
    source_filename: str = Form("backup.zip"),
    is_encrypted: str = Form("false"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Confirm and execute full database and uploads restore."""
    import base64

    try:
        plain_zip_bytes = base64.b64decode(backup_zip_b64)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Некорректный архив резервной копии",
        )

    enc_flag = str(is_encrypted).lower() in ("true", "1", "yes", "on")

    try:
        confirm_restore_backup(
            plain_zip_bytes=plain_zip_bytes,
            confirmation_text=confirmation_text,
            actor_user_id=current_user.id,
            filename=source_filename,
            is_encrypted=enc_flag,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    return RedirectResponse(
        url="/admin/service?active_tab=backup&message=База+данных+и+вложения+успешно+восстановлены",
        status_code=status.HTTP_302_FOUND,
    )

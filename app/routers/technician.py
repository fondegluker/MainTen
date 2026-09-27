"""Technician routes for CFMS (Iteration 5)."""

import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin, require_technician
from app.core.database import get_db
from app.core.i18n import format_date_localized, get_locale, translate
from app.models.models import (
    Computer,
    MaintenanceEvent,
    MaintenanceEventAttachment,
    MaintenanceEventCheck,
    MaintenanceEventStatus,
    MaintenanceProtocolItem,
    User,
    UserRole,
)
from app.routers.web import context_with_defaults
from app.services.audit_service import log_audit
from app.services.scheduling_service import (
    compute_next_maintenance_due_at,
    get_technician_events_in_range,
    get_technician_month_grid,
)

router = APIRouter(prefix="/technician", tags=["technician"])
templates = Jinja2Templates(directory="app/templates")

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

UPLOAD_DIR = "/app/uploads/attachments"


def _check_event_access(event: MaintenanceEvent, user: User) -> None:
    """Helper to enforce role access: TECHNICIAN sees only own events, ADMIN sees all, others 403."""
    if user.role.value in ["admin", "ADMIN"]:
        return
    if user.role.value in ["technician", "TECHNICIAN"]:
        if event.technician_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.get("/day", response_class=HTMLResponse)
@router.get("/schedule", response_class=HTMLResponse)
def technician_day_schedule(
    request: Request,
    date_str: str | None = Query(None, alias="date"),
    technician_id: int | None = Query(None),
    message: str | None = None,
    error: str | None = None,
    current_user: User = Depends(require_technician),
    db: Session = Depends(get_db),
):
    """Technician day view (default today) showing scheduled events."""
    today_d = datetime.now(timezone.utc).date()

    if date_str and date_str.strip():
        try:
            target_date = date.fromisoformat(date_str.strip())
        except ValueError:
            target_date = today_d
    else:
        target_date = today_d

    # Determine target technician
    if current_user.role.value in ["admin", "ADMIN"] and technician_id:
        target_tech_id = technician_id
    else:
        target_tech_id = current_user.id

    target_tech = db.query(User).filter(User.id == target_tech_id).first()

    events = (
        db.query(MaintenanceEvent)
        .filter(
            MaintenanceEvent.technician_id == target_tech_id,
            MaintenanceEvent.scheduled_date == target_date,
        )
        .order_by(MaintenanceEvent.scheduled_slot.asc().nulls_last(), MaintenanceEvent.id.asc())
        .all()
    )

    prev_date = (target_date - timedelta(days=1)).isoformat()
    next_date = (target_date + timedelta(days=1)).isoformat()
    all_technicians = db.query(User).filter(User.role == UserRole.TECHNICIAN, User.is_active == True).all()

    active_locale = get_locale(request, current_user.locale)

    return templates.TemplateResponse(
        "technician/schedule.html",
        context_with_defaults(
            request,
            current_user,
            {
                "events": events,
                "target_date": target_date,
                "target_date_str": target_date.isoformat(),
                "formatted_date": format_date_localized(target_date, locale=active_locale),
                "prev_date": prev_date,
                "next_date": next_date,
                "target_tech": target_tech,
                "all_technicians": all_technicians,
                "message": message,
                "error": error,
                "active_view": "day",
            },
        ),
    )


@router.get("/week", response_class=HTMLResponse)
def technician_week_schedule(
    request: Request,
    date_str: str | None = Query(None, alias="date"),
    technician_id: int | None = Query(None),
    current_user: User = Depends(require_technician),
    db: Session = Depends(get_db),
):
    """Technician week view showing 7 days starting from Monday."""
    today_d = datetime.now(timezone.utc).date()

    if date_str and date_str.strip():
        try:
            ref_date = date.fromisoformat(date_str.strip())
        except ValueError:
            ref_date = today_d
    else:
        ref_date = today_d

    # Find Monday of week
    week_monday = ref_date - timedelta(days=ref_date.weekday())
    week_sunday = week_monday + timedelta(days=6)

    # Determine target technician
    if current_user.role.value in ["admin", "ADMIN"] and technician_id:
        target_tech_id = technician_id
    else:
        target_tech_id = current_user.id

    target_tech = db.query(User).filter(User.id == target_tech_id).first()

    events = get_technician_events_in_range(db, target_tech_id, week_monday, week_sunday)

    # Group events by day
    week_days = []
    events_by_date: dict[date, list[MaintenanceEvent]] = {}
    for ev in events:
        if ev.scheduled_date:
            events_by_date.setdefault(ev.scheduled_date, []).append(ev)

    active_locale = get_locale(request, current_user.locale)

    for i in range(7):
        day_date = week_monday + timedelta(days=i)
        day_events = events_by_date.get(day_date, [])
        week_days.append(
            {
                "date": day_date,
                "date_str": day_date.isoformat(),
                "formatted": format_date_localized(day_date, locale=active_locale),
                "is_today": (day_date == today_d),
                "events": day_events,
            }
        )

    prev_week_date = (week_monday - timedelta(days=7)).isoformat()
    next_week_date = (week_monday + timedelta(days=7)).isoformat()
    all_technicians = db.query(User).filter(User.role == UserRole.TECHNICIAN, User.is_active == True).all()

    return templates.TemplateResponse(
        "technician/week.html",
        context_with_defaults(
            request,
            current_user,
            {
                "week_days": week_days,
                "week_monday": week_monday,
                "week_sunday": week_sunday,
                "prev_week_date": prev_week_date,
                "next_week_date": next_week_date,
                "target_tech": target_tech,
                "all_technicians": all_technicians,
                "active_view": "week",
            },
        ),
    )


@router.get("/month", response_class=HTMLResponse)
def technician_month_schedule(
    request: Request,
    month_str: str | None = Query(None, alias="month"),
    align_param: int | None = Query(None, alias="align"),
    technician_id: int | None = Query(None),
    current_user: User = Depends(require_technician),
    db: Session = Depends(get_db),
):
    """Technician month view with 32-cell grid and align-to-today toggle."""
    today_d = datetime.now(timezone.utc).date()

    # Determine target month (year, month)
    if month_str and month_str.strip():
        try:
            parts = month_str.strip().split("-")
            target_year = int(parts[0])
            target_month = int(parts[1])
        except (ValueError, IndexError):
            target_year = today_d.year
            target_month = today_d.month
    else:
        target_year = today_d.year
        target_month = today_d.month

    # Determine align toggle state (default ON = True)
    if align_param is not None:
        align_toggle = bool(align_param == 1)
    else:
        cookie_val = request.cookies.get("align_toggle")
        if cookie_val is not None:
            align_toggle = bool(cookie_val == "1")
        else:
            align_toggle = True

    # Determine target technician
    if current_user.role.value in ["admin", "ADMIN"] and technician_id:
        target_tech_id = technician_id
    else:
        target_tech_id = current_user.id

    target_tech = db.query(User).filter(User.id == target_tech_id).first()
    all_technicians = db.query(User).filter(User.role == UserRole.TECHNICIAN, User.is_active == True).all()

    month_grid = get_technician_month_grid(
        year=target_year,
        month=target_month,
        align=align_toggle,
        today=today_d,
        technician_id=target_tech_id,
        db=db,
    )

    resp = templates.TemplateResponse(
        "technician/month.html",
        context_with_defaults(
            request,
            current_user,
            {
                "month_grid": month_grid,
                "target_tech": target_tech,
                "all_technicians": all_technicians,
                "align_toggle": align_toggle,
                "active_view": "month",
            },
        ),
    )
    resp.set_cookie("align_toggle", "1" if align_toggle else "0")
    return resp


@router.get("/unplanned", response_class=HTMLResponse)
def unplanned_event_form(
    request: Request,
    current_user: User = Depends(require_technician),
    db: Session = Depends(get_db),
):
    """Form to create an unplanned maintenance event."""
    computers = db.query(Computer).filter(Computer.status == "active").order_by(Computer.hostname.asc()).all()
    today_str = datetime.now(timezone.utc).date().isoformat()

    return templates.TemplateResponse(
        "technician/unplanned_form.html",
        context_with_defaults(
            request,
            current_user,
            {
                "computers": computers,
                "today_str": today_str,
            },
        ),
    )


@router.post("/unplanned")
def create_unplanned_event(
    request: Request,
    computer_id: int = Form(...),
    scheduled_date_str: str = Form(..., alias="scheduled_date"),
    scheduled_slot: str | None = Form(None),
    comment: str | None = Form(None),
    current_user: User = Depends(require_technician),
    db: Session = Depends(get_db),
):
    """Create an unplanned maintenance event."""
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Компьютер не найден")

    try:
        sched_date = date.fromisoformat(scheduled_date_str.strip())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Некорректный формат даты")

    event = MaintenanceEvent(
        computer_id=computer.id,
        technician_id=current_user.id,
        scheduled_date=sched_date,
        scheduled_slot=scheduled_slot.strip() if scheduled_slot else None,
        status=MaintenanceEventStatus.PLANNED,
        comment=comment.strip() if comment else None,
        is_unplanned=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.flush()

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="create_unplanned_event",
        entity="maintenance_events",
        entity_id=event.id,
        after={
            "computer_id": computer.id,
            "scheduled_date": sched_date.isoformat(),
            "is_unplanned": True,
            "technician_id": current_user.id,
        },
    )
    db.commit()

    return RedirectResponse(
        url=f"/technician/schedule?date={sched_date.isoformat()}&message=Внеплановое+ТО+успешно+создано",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/events/{event_id}", response_class=HTMLResponse)
def technician_event_detail(
    event_id: int,
    request: Request,
    message: str | None = None,
    error: str | None = None,
    current_user: User = Depends(require_technician),
    db: Session = Depends(get_db),
):
    """Event detail page showing protocol checklist, comments, attachments, and actions."""
    event = db.query(MaintenanceEvent).filter(MaintenanceEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Мероприятие ТО не найдено")

    _check_event_access(event, current_user)

    # Active protocol items
    active_protocol_items = (
        db.query(MaintenanceProtocolItem)
        .filter(MaintenanceProtocolItem.is_active == True)
        .order_by(MaintenanceProtocolItem.order_index.asc())
        .all()
    )

    # Existing checks map
    existing_checks = {check.protocol_item_id: check for check in event.checks}

    active_locale = get_locale(request, current_user.locale)

    return templates.TemplateResponse(
        "technician/event_detail.html",
        context_with_defaults(
            request,
            current_user,
            {
                "event": event,
                "protocol_items": active_protocol_items,
                "existing_checks": existing_checks,
                "formatted_date": format_date_localized(event.scheduled_date, locale=active_locale)
                if event.scheduled_date
                else "",
                "message": message,
                "error": error,
            },
        ),
    )


@router.post("/events/{event_id}/start")
def start_maintenance_event(
    event_id: int,
    current_user: User = Depends(require_technician),
    db: Session = Depends(get_db),
):
    """Transition event status from planned -> in_progress and snapshot started_at."""
    event = db.query(MaintenanceEvent).filter(MaintenanceEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Мероприятие ТО не найдено")

    _check_event_access(event, current_user)

    if event.status != MaintenanceEventStatus.PLANNED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Старт возможен только для запланированных мероприятий",
        )

    before_status = event.status.value
    event.status = MaintenanceEventStatus.IN_PROGRESS
    event.started_at = datetime.now(timezone.utc)
    event.updated_at = datetime.now(timezone.utc)

    # Create empty checks for active protocol items if not already present
    active_items = db.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.is_active == True).all()
    existing_item_ids = {c.protocol_item_id for c in event.checks}

    for item in active_items:
        if item.id not in existing_item_ids:
            chk = MaintenanceEventCheck(
                event_id=event.id,
                protocol_item_id=item.id,
                is_done=False,
            )
            db.add(chk)

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="start_maintenance_event",
        entity="maintenance_events",
        entity_id=event.id,
        before={"status": before_status},
        after={"status": event.status.value, "started_at": event.started_at.isoformat()},
    )
    db.commit()

    return RedirectResponse(
        url=f"/technician/events/{event.id}?message=Обслуживание+начато",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/events/{event_id}/finish")
async def finish_maintenance_event(
    event_id: int,
    request: Request,
    comment: str | None = Form(None),
    current_user: User = Depends(require_technician),
    db: Session = Depends(get_db),
):
    """Finish maintenance event. Validates every active protocol item is checked (done or not done).
    Sets status=done, finished_at=now, recalculates computer's last_maintenance_at and next_maintenance_due_at via shared helper.
    """
    event = db.query(MaintenanceEvent).filter(MaintenanceEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Мероприятие ТО не найдено")

    _check_event_access(event, current_user)

    if event.status != MaintenanceEventStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Завершение возможно только для мероприятий в процессе",
        )

    form_data = await request.form()
    active_items = db.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.is_active == True).all()

    # Verify that form submitted status for all active protocol items
    checks_dict = {}
    missing_items = []

    for item in active_items:
        check_key = f"check_{item.id}"
        comment_key = f"comment_{item.id}"

        # check_key must be explicitly submitted in form ("done" or "not_done")
        if check_key not in form_data:
            missing_items.append(item.title_ru)
        else:
            is_done_val = form_data[check_key] == "done"
            item_comment = str(form_data.get(comment_key, "")).strip() or None
            checks_dict[item.id] = (is_done_val, item_comment)

    if missing_items:
        active_locale = get_locale(request, current_user.locale)
        err_msg = translate("all_items_required", active_locale)
        return RedirectResponse(
            url=f"/technician/events/{event.id}?error={err_msg}",
            status_code=status.HTTP_302_FOUND,
        )

    # Save protocol item checks
    for item_id, (is_done_val, item_comment) in checks_dict.items():
        chk = (
            db.query(MaintenanceEventCheck)
            .filter(MaintenanceEventCheck.event_id == event.id, MaintenanceEventCheck.protocol_item_id == item_id)
            .first()
        )
        if chk:
            chk.is_done = is_done_val
            chk.comment = item_comment
            chk.checked_at = datetime.now(timezone.utc)
        else:
            chk = MaintenanceEventCheck(
                event_id=event.id,
                protocol_item_id=item_id,
                is_done=is_done_val,
                comment=item_comment,
                checked_at=datetime.now(timezone.utc),
            )
            db.add(chk)

    before_status = event.status.value
    now_dt = datetime.now(timezone.utc)

    event.status = MaintenanceEventStatus.DONE
    event.finished_at = now_dt
    if comment and comment.strip():
        event.comment = comment.strip()
    event.updated_at = now_dt

    # Side effect: update computer's last_maintenance_at and next_maintenance_due_at via shared helper
    computer = event.computer
    computer.last_maintenance_at = now_dt
    next_due_d = compute_next_maintenance_due_at(computer, db, base_date=now_dt.date())
    computer.next_maintenance_due_at = datetime.combine(next_due_d, datetime.min.time())

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="finish_maintenance_event",
        entity="maintenance_events",
        entity_id=event.id,
        before={"status": before_status},
        after={
            "status": event.status.value,
            "finished_at": now_dt.isoformat(),
            "computer_last_maintenance_at": computer.last_maintenance_at.isoformat(),
            "computer_next_maintenance_due_at": computer.next_maintenance_due_at.isoformat(),
        },
    )
    db.commit()

    return RedirectResponse(
        url=f"/technician/events/{event.id}?message=Обслуживание+успешно+завершено",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/events/{event_id}/missed")
def mark_event_as_missed(
    event_id: int,
    request: Request,
    reason: str = Form(...),
    current_user: User = Depends(require_technician),
    db: Session = Depends(get_db),
):
    """Mark event as missed with mandatory reason comment."""
    event = db.query(MaintenanceEvent).filter(MaintenanceEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Мероприятие ТО не найдено")

    _check_event_access(event, current_user)

    reason_str = reason.strip() if reason else ""
    if not reason_str:
        active_locale = get_locale(request, current_user.locale)
        err_msg = translate("missed_reason_required", active_locale)
        return RedirectResponse(
            url=f"/technician/events/{event.id}?error={err_msg}",
            status_code=status.HTTP_302_FOUND,
        )

    if event.status not in (MaintenanceEventStatus.PLANNED, MaintenanceEventStatus.IN_PROGRESS):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Отметить пропущенным можно только запланированные мероприятия или в процессе",
        )

    before_status = event.status.value
    event.status = MaintenanceEventStatus.MISSED
    event.comment = f"Пропущено: {reason_str}"
    event.updated_at = datetime.now(timezone.utc)

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="mark_event_missed",
        entity="maintenance_events",
        entity_id=event.id,
        before={"status": before_status},
        after={"status": event.status.value, "reason": reason_str},
    )
    db.commit()

    return RedirectResponse(
        url=f"/technician/events/{event.id}?message=Отмечено+как+пропущенное",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/events/{event_id}/attachments")
async def upload_event_attachment(
    event_id: int,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(require_technician),
    db: Session = Depends(get_db),
):
    """Upload attachment file for event with max 10MB size and mime-type validation."""
    event = db.query(MaintenanceEvent).filter(MaintenanceEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Мероприятие ТО не найдено")

    _check_event_access(event, current_user)
    active_locale = get_locale(request, current_user.locale)

    content_bytes = await file.read()
    if len(content_bytes) > MAX_FILE_SIZE_BYTES:
        err_msg = translate("file_too_large", active_locale)
        return RedirectResponse(
            url=f"/technician/events/{event.id}?error={err_msg}",
            status_code=status.HTTP_302_FOUND,
        )

    content_type = file.content_type.lower() if file.content_type else "application/octet-stream"
    if not any(content_type.startswith(prefix) for prefix in ["image/", "application/pdf", "text/plain"]):
        err_msg = translate("invalid_file_type", active_locale)
        return RedirectResponse(
            url=f"/technician/events/{event.id}?error={err_msg}",
            status_code=status.HTTP_302_FOUND,
        )

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_ext = os.path.splitext(file.filename)[1] if file.filename else ""
    saved_filename = f"{uuid.uuid4().hex}{file_ext}"
    blob_path = os.path.join(UPLOAD_DIR, saved_filename)

    with open(blob_path, "wb") as f:
        f.write(content_bytes)

    attachment = MaintenanceEventAttachment(
        event_id=event.id,
        filename=file.filename or "file",
        mime=content_type,
        blob_path=blob_path,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(attachment)

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="upload_event_attachment",
        entity="maintenance_event_attachments",
        entity_id=event.id,
        after={"filename": file.filename, "size": len(content_bytes), "mime": content_type},
    )
    db.commit()

    return RedirectResponse(
        url=f"/technician/events/{event.id}?message=Файл+успешно+загружен",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/events/{event_id}/edit")
async def edit_maintenance_event(
    event_id: int,
    request: Request,
    comment: str | None = Form(None),
    scheduled_date_str: str | None = Form(None, alias="scheduled_date"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Edit maintenance event (checklist, comments, scheduled_date for admin).
    Allowed for assigned technician or admin. Does NOT recalculate computer due dates.
    """
    event = db.query(MaintenanceEvent).filter(MaintenanceEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    role_val = current_user.role.value.lower() if hasattr(current_user.role, "value") else str(current_user.role).lower()

    if role_val == "technician" and event.technician_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if role_val not in ("admin", "technician"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    form_data = await request.form()

    # Reject status or computer/technician re-assignments
    if "status" in form_data and str(form_data["status"]).lower() != event.status.value.lower():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot change status via edit")
    if "computer_id" in form_data and str(form_data["computer_id"]) != str(event.computer_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot change computer_id")
    if "technician_id" in form_data and str(form_data["technician_id"]) != str(event.technician_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot change technician_id")

    before_json = {
        "comment": event.comment,
        "scheduled_date": event.scheduled_date.isoformat() if event.scheduled_date else None,
        "checks": {c.protocol_item_id: {"is_done": c.is_done, "comment": c.comment} for c in event.checks},
    }

    # Scheduled date change (ADMIN only)
    if scheduled_date_str and scheduled_date_str.strip():
        try:
            new_date = date.fromisoformat(scheduled_date_str.strip())
            if new_date != event.scheduled_date:
                if role_val != "admin":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Only ADMIN can edit scheduled_date",
                    )
                event.scheduled_date = new_date
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid date format")

    if comment is not None:
        event.comment = comment.strip() if comment.strip() else None

    # Update protocol checks
    active_items = db.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.is_active == True).all()
    for item in active_items:
        check_key = f"check_{item.id}"
        comment_key = f"comment_{item.id}"

        if check_key in form_data:
            is_done_val = form_data[check_key] == "done"
            item_comment = str(form_data.get(comment_key, "")).strip() or None

            chk = (
                db.query(MaintenanceEventCheck)
                .filter(MaintenanceEventCheck.event_id == event.id, MaintenanceEventCheck.protocol_item_id == item.id)
                .first()
            )
            if chk:
                chk.is_done = is_done_val
                chk.comment = item_comment
                chk.checked_at = datetime.now(timezone.utc)
            else:
                chk = MaintenanceEventCheck(
                    event_id=event.id,
                    protocol_item_id=item.id,
                    is_done=is_done_val,
                    comment=item_comment,
                    checked_at=datetime.now(timezone.utc),
                )
                db.add(chk)

    event.updated_at = datetime.now(timezone.utc)

    after_json = {
        "comment": event.comment,
        "scheduled_date": event.scheduled_date.isoformat() if event.scheduled_date else None,
        "checks": {c.protocol_item_id: {"is_done": c.is_done, "comment": c.comment} for c in event.checks},
    }

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="edit_closed_event",
        entity="maintenance_events",
        entity_id=event.id,
        before=before_json,
        after=after_json,
    )
    db.commit()

    return RedirectResponse(
        url=f"/technician/events/{event.id}?message=Изменения+успешно+сохранены",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/events/{event_id}/attachments/{att_id}/delete")
def delete_event_attachment(
    event_id: int,
    att_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete an event attachment (ADMIN only)."""
    event = db.query(MaintenanceEvent).filter(MaintenanceEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    attachment = (
        db.query(MaintenanceEventAttachment)
        .filter(
            MaintenanceEventAttachment.id == att_id,
            MaintenanceEventAttachment.event_id == event_id,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    if os.path.exists(attachment.blob_path):
        try:
            os.remove(attachment.blob_path)
        except OSError:
            pass

    db.delete(attachment)
    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="delete_event_attachment",
        entity="maintenance_event_attachments",
        entity_id=attachment.id,
        before={"filename": attachment.filename, "event_id": event_id},
    )
    db.commit()

    return RedirectResponse(
        url=f"/technician/events/{event.id}?message=Вложение+удалено",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/events/{event_id}/attachments/{att_id}")
def serve_event_attachment(
    event_id: int,
    att_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Serve attachment file with appropriate Content-Type and Content-Disposition.
    Restricted to assigned technician and ADMIN.
    """
    role_val = current_user.role.value.lower() if hasattr(current_user.role, "value") else str(current_user.role).lower()
    if role_val not in ("admin", "technician"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    event = db.query(MaintenanceEvent).filter(MaintenanceEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    if role_val == "technician" and event.technician_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    attachment = (
        db.query(MaintenanceEventAttachment)
        .filter(
            MaintenanceEventAttachment.id == att_id,
            MaintenanceEventAttachment.event_id == event_id,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    if not os.path.exists(attachment.blob_path):
        logger.warning("Attachment file missing on disk: att_id=%s, path=%s", att_id, attachment.blob_path)
        active_locale = get_locale(request, current_user.locale)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate("file_missing_on_server", active_locale),
        )

    file_ext = os.path.splitext(attachment.filename)[1].lower()
    mime = attachment.mime.lower() if attachment.mime else ""

    inline_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".pdf", ".txt", ".log", ".md", ".csv"}
    is_inline = (
        file_ext in inline_exts
        or mime.startswith("image/")
        or mime in ("application/pdf", "text/plain", "text/markdown", "text/csv")
    )

    disposition_type = "inline" if is_inline else "attachment"

    headers = {
        "Content-Disposition": f'{disposition_type}; filename="{attachment.filename}"',
    }

    if file_ext in (".txt", ".log") or mime == "text/plain":
        media_type = "text/plain; charset=utf-8"
        headers["X-Content-Type-Options"] = "nosniff"
    elif file_ext == ".md" or mime == "text/markdown":
        media_type = "text/markdown; charset=utf-8"
        headers["X-Content-Type-Options"] = "nosniff"
    elif file_ext == ".csv" or mime == "text/csv":
        media_type = "text/csv; charset=utf-8"
        headers["X-Content-Type-Options"] = "nosniff"
    elif mime:
        media_type = mime
    else:
        media_type = "application/octet-stream"

    response = FileResponse(path=attachment.blob_path, media_type=media_type)
    for k, v in headers.items():
        response.headers[k] = v
    return response

"""User routes for CFMS (Iteration 4)."""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.models import Computer, MaintenanceEvent, MaintenanceEventStatus, User, UserRole
from app.routers.web import context_with_defaults
from app.services.scheduling_service import (
    compute_next_maintenance_due_at,
    get_available_dates,
    is_notification_window_open,
    schedule_maintenance,
)

router = APIRouter(prefix="/user", tags=["user"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/my-computers", response_class=HTMLResponse)
def user_computers_page(
    request: Request,
    message: str | None = None,
    error: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Page listing all computers owned by current user with history and schedule prompt."""
    if current_user.role == UserRole.ADMIN:
        computers = db.query(Computer).all()
    else:
        computers = db.query(Computer).filter(Computer.owner_user_id == current_user.id).all()

    computers_data = []
    today = datetime.now(timezone.utc).date()

    for comp in computers:
        if not comp.next_maintenance_due_at:
            comp.next_maintenance_due_at = compute_next_maintenance_due_at(comp, db)
            db.add(comp)

        due_date = (
            comp.next_maintenance_due_at.date()
            if hasattr(comp.next_maintenance_due_at, "date")
            else comp.next_maintenance_due_at
        )
        window_open = is_notification_window_open(comp, db, today=today)

        # Get planned event if any
        planned_event = (
            db.query(MaintenanceEvent)
            .filter(MaintenanceEvent.computer_id == comp.id, MaintenanceEvent.status == MaintenanceEventStatus.PLANNED)
            .first()
        )

        # Get past maintenance events with details
        past_events = (
            db.query(MaintenanceEvent)
            .filter(
                MaintenanceEvent.computer_id == comp.id,
                MaintenanceEvent.status.in_(
                    [MaintenanceEventStatus.DONE, MaintenanceEventStatus.MISSED, MaintenanceEventStatus.CANCELLED]
                ),
            )
            .order_by(MaintenanceEvent.scheduled_date.desc())
            .all()
        )

        computers_data.append(
            {
                "computer": comp,
                "due_date": due_date,
                "window_open": window_open,
                "planned_event": planned_event,
                "past_events": past_events,
                "is_manager": len(computers) > 1,
            }
        )

    db.commit()

    return templates.TemplateResponse(
        "user_computers.html",
        context_with_defaults(
            request,
            current_user,
            {
                "computers_data": computers_data,
                "message": message,
                "error": error,
                "is_manager_user": len(computers) > 1,
            },
        ),
    )


@router.get("/schedule/{computer_id}", response_class=HTMLResponse)
def schedule_date_picker_page(
    computer_id: int,
    request: Request,
    error: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Page displaying available working days for user to pick a maintenance date."""
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        return RedirectResponse(url="/user/my-computers?error=Компьютер+не+найден", status_code=status.HTTP_302_FOUND)

    if current_user.role != UserRole.ADMIN and computer.owner_user_id != current_user.id:
        return RedirectResponse(url="/user/my-computers?error=Доступ+запрещен", status_code=status.HTTP_302_FOUND)

    available_dates = get_available_dates(computer.id, db)

    planned_event = (
        db.query(MaintenanceEvent)
        .filter(MaintenanceEvent.computer_id == computer.id, MaintenanceEvent.status == MaintenanceEventStatus.PLANNED)
        .first()
    )

    return templates.TemplateResponse(
        "user_schedule.html",
        context_with_defaults(
            request,
            current_user,
            {
                "computer": computer,
                "available_dates": available_dates,
                "planned_event": planned_event,
                "error": error,
            },
        ),
    )


@router.post("/schedule/{computer_id}")
def submit_schedule_date(
    computer_id: int,
    scheduled_date_str: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit selected maintenance date for computer."""
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        return RedirectResponse(url="/user/my-computers?error=Компьютер+не+найден", status_code=status.HTTP_302_FOUND)

    if current_user.role != UserRole.ADMIN and computer.owner_user_id != current_user.id:
        return RedirectResponse(url="/user/my-computers?error=Доступ+запрещен", status_code=status.HTTP_302_FOUND)

    try:
        selected_date = date.fromisoformat(scheduled_date_str)
        today = datetime.now(timezone.utc).date()
        if selected_date <= today:
            return RedirectResponse(
                url=f"/user/schedule/{computer_id}?error=Выберите+будущую+дату", status_code=status.HTTP_302_FOUND
            )

        schedule_maintenance(computer.id, selected_date, current_user.id, db)
        return RedirectResponse(
            url="/user/my-computers?message=Дата+технического+обслуживания+успешно+запланирована",
            status_code=status.HTTP_302_FOUND,
        )
    except ValueError as exc:
        return RedirectResponse(url=f"/user/schedule/{computer_id}?error={exc}", status_code=status.HTTP_302_FOUND)

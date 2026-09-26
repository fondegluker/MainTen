"""Agent API endpoints for Windows CFMS Agent (Iteration 4 / Iteration 6 contract)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.models import Notification, User

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/notifications")
def get_agent_notifications(
    user_id: int = Query(...),
    unacknowledged_only: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve notifications for a given user ID to be displayed by the Windows desktop agent."""
    if current_user.role.value not in ["admin", "ADMIN"] and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    query = db.query(Notification).filter(Notification.user_id == user_id)
    if unacknowledged_only:
        query = query.filter(Notification.acknowledged_at == None)

    notifications = query.order_by(Notification.sent_at.desc()).all()

    items = []
    for n in notifications:
        items.append(
            {
                "id": n.id,
                "user_id": n.user_id,
                "computer_id": n.computer_id,
                "event_id": n.event_id,
                "channel": n.channel,
                "payload": n.payload_json,
                "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                "acknowledged_at": n.acknowledged_at.isoformat() if n.acknowledged_at else None,
            }
        )

    return {"notifications": items, "count": len(items)}


@router.post("/notifications/{notification_id}/ack")
def acknowledge_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Acknowledge notification receipt from Windows desktop agent."""
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    if current_user.role.value not in ["admin", "ADMIN"] and notif.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not notif.acknowledged_at:
        notif.acknowledged_at = datetime.now(timezone.utc)
        db.commit()

    return {
        "status": "success",
        "notification_id": notif.id,
        "acknowledged_at": notif.acknowledged_at.isoformat(),
    }

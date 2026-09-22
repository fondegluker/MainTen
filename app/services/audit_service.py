from typing import Any

from sqlalchemy.orm import Session

from app.models.models import AuditLog


def log_audit(
    db: Session,
    actor_user_id: int | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        before_json=before,
        after_json=after
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry

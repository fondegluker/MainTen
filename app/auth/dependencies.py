
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.tokens import verify_session_cookie
from app.core.database import get_db
from app.models.models import User, UserRole


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    session_token = request.cookies.get("session")
    if not session_token:
        return None
    user_id = verify_session_cookie(session_token)
    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    return user

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user_optional(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user

class RoleChecker:
    def __init__(self, allowed_roles: list[UserRole]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: User = Depends(get_current_user)) -> User:
        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted",
            )
        return user

require_admin = RoleChecker([UserRole.ADMIN])
require_technician = RoleChecker([UserRole.ADMIN, UserRole.TECHNICIAN])
require_observer = RoleChecker([UserRole.ADMIN, UserRole.OBSERVER])

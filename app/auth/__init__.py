from app.auth.base import AuthCredentials, BaseAuthProvider
from app.auth.dependencies import (
    get_current_user,
    get_current_user_optional,
    require_admin,
    require_observer,
    require_technician,
)
from app.auth.providers import AdAuthProvider, LocalAuthProvider
from app.auth.tokens import (
    generate_magic_link_token,
    generate_session_cookie,
    verify_magic_link_token,
    verify_session_cookie,
)

__all__ = [
    "AdAuthProvider",
    "AuthCredentials",
    "BaseAuthProvider",
    "LocalAuthProvider",
    "generate_magic_link_token",
    "generate_session_cookie",
    "get_current_user",
    "get_current_user_optional",
    "require_admin",
    "require_observer",
    "require_technician",
    "verify_magic_link_token",
    "verify_session_cookie",
]

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

MAGIC_LINK_SALT = "cfms-magic-link-salt"


def generate_magic_link_token(user_id: int, computer_id: int | None = None) -> str:
    data = {"user_id": user_id}
    if computer_id is not None:
        data["computer_id"] = computer_id
    return serializer.dumps(data, salt=MAGIC_LINK_SALT)


def verify_magic_link_token(token: str, max_age_seconds: int = 86400 * 30) -> dict | None:
    """Verify magic link token. Default validity is 30 days."""
    try:
        data = serializer.loads(token, salt=MAGIC_LINK_SALT, max_age=max_age_seconds)
        return data
    except (BadSignature, SignatureExpired):
        return None


SESSION_SALT = "cfms-session-cookie-salt"


def generate_session_cookie(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id}, salt=SESSION_SALT)


def verify_session_cookie(cookie_value: str, max_age_seconds: int = 86400 * 7) -> int | None:
    try:
        data = serializer.loads(cookie_value, salt=SESSION_SALT, max_age=max_age_seconds)
        return data.get("user_id")
    except (BadSignature, SignatureExpired):
        return None

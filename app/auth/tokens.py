from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

MAGIC_LINK_SALT = "cfms-magic-link-salt"


def generate_magic_link_token(user_id: int, computer_id: int | None = None, token_version: int = 0) -> str:
    data = {"user_id": user_id, "version": token_version}
    if computer_id is not None:
        data["computer_id"] = computer_id
    return serializer.dumps(data, salt=MAGIC_LINK_SALT)


def verify_magic_link_token(token: str, db=None, max_age_seconds: int = 86400 * 30) -> dict | None:
    """Verify magic link token. Default validity is 30 days."""
    try:
        data = serializer.loads(token, salt=MAGIC_LINK_SALT, max_age=max_age_seconds)
        if db is not None:
            user_id = data.get("user_id")
            token_ver = data.get("version", 0)
            from app.models.models import Setting

            setting = db.query(Setting).filter(Setting.key == f"magic_token_version_{user_id}").first()
            current_ver = setting.value_json if setting else 0
            if token_ver < current_ver:
                return None
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

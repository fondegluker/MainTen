from passlib.context import CryptContext
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.base import AuthCredentials, BaseAuthProvider
from app.models.models import User

pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


class LocalAuthProvider(BaseAuthProvider):
    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        if not hashed_password:
            return False
        return pwd_context.verify(plain_password, hashed_password)

    def authenticate(self, db: Session, credentials: AuthCredentials) -> User | None:
        if not credentials.password or not credentials.username_or_email:
            return None

        identifier = credentials.username_or_email.strip().lower()

        user = (
            db.query(User)
            .filter((func.lower(User.username) == identifier) | (func.lower(User.email_or_login) == identifier))
            .first()
        )
        if not user or not user.is_active or not user.password_hash:
            return None

        if self.verify_password(credentials.password.strip(), user.password_hash):
            return user
        return None

    def get_user(self, db: Session, user_id: int) -> User | None:
        return db.query(User).filter(User.id == user_id, User.is_active == True).first()


class AdAuthProvider(BaseAuthProvider):
    """
    Active Directory / LDAP Auth Provider Stub.
    Interface designed for future LDAP plugin implementation.
    """

    def __init__(self, ldap_server: str | None = None, domain: str | None = None):
        self.ldap_server = ldap_server
        self.domain = domain

    def authenticate(self, db: Session, credentials: AuthCredentials) -> User | None:
        raise NotImplementedError("Active Directory / LDAP authentication is not currently configured.")

    def get_user(self, db: Session, user_id: int) -> User | None:
        return db.query(User).filter(User.id == user_id, User.is_active == True).first()

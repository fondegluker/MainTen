from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models.models import User


class AuthCredentials:
    def __init__(self, username_or_email: str, password: str | None = None, token: str | None = None):
        self.username_or_email = username_or_email
        self.password = password
        self.token = token


class BaseAuthProvider(ABC):
    @abstractmethod
    def authenticate(self, db: Session, credentials: AuthCredentials) -> User | None:
        """Authenticate user with credentials and return User instance if valid."""

    @abstractmethod
    def get_user(self, db: Session, user_id: int) -> User | None:
        """Retrieve user by ID."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.providers import AdAuthProvider, LocalAuthProvider
from app.auth.tokens import generate_magic_link_token
from app.core.database import Base, get_db
from app.main import app
from app.models.models import Computer, User, UserRole

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_app.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_app.db"):
        os.remove("./test_app.db")

@pytest.fixture
def db_session(setup_db):
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_local_auth_provider(db_session):
    provider = LocalAuthProvider()
    hashed = provider.hash_password("admin123")

    admin = User(
        username="admin_test",
        email_or_login="admin@cfms.local",
        password_hash=hashed,
        role=UserRole.ADMIN,
        locale="ru",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    from app.auth.base import AuthCredentials

    # Valid login
    auth_user = provider.authenticate(db_session, AuthCredentials("admin_test", "admin123"))
    assert auth_user is not None
    assert auth_user.username == "admin_test"

    # Invalid password
    auth_user_bad = provider.authenticate(db_session, AuthCredentials("admin_test", "wrongpass"))
    assert auth_user_bad is None

def test_ad_auth_provider_stub(db_session):
    provider = AdAuthProvider()
    from app.auth.base import AuthCredentials
    with pytest.raises(NotImplementedError):
        provider.authenticate(db_session, AuthCredentials("ad_user", "pass"))

def test_web_auth_login_flow(client, db_session):
    provider = LocalAuthProvider()
    admin = User(
        username="admin_login",
        email_or_login="admin_login@cfms.local",
        password_hash=provider.hash_password("secret123"),
        role=UserRole.ADMIN,
        locale="ru",
    )
    db_session.add(admin)
    db_session.commit()

    response = client.post(
        "/auth/login",
        data={"username": "admin_login", "password": "secret123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "session" in response.cookies

    # Access protected admin dashboard with session cookie
    client.cookies.update(response.cookies)
    dash_response = client.get("/admin/dashboard")
    assert dash_response.status_code == 200
    assert "Панель администратора" in dash_response.text

def test_magic_link_flow(client, db_session):
    user = User(
        username="user1",
        email_or_login="user1@cfms.local",
        role=UserRole.USER,
        locale="en",
    )
    db_session.add(user)
    db_session.commit()

    computer = Computer(
        hostname="PC-USER-01",
        owner_user_id=user.id,
        status="active"
    )
    db_session.add(computer)
    db_session.commit()

    token = generate_magic_link_token(user.id, computer.id)
    response = client.get(f"/auth/magic-link?token={token}", follow_redirects=True)
    assert response.status_code == 200
    assert "PC-USER-01" in response.text

def test_locale_switcher(client):
    response = client.get("/set-locale?locale=en", follow_redirects=False)
    assert response.status_code == 302
    assert "locale" in response.cookies
    assert response.cookies["locale"] == "en"

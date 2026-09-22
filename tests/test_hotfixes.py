import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.providers import LocalAuthProvider
from app.core.database import Base, get_db
from app.main import app
from app.models.models import User, UserRole

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_hotfixes.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_hotfixes.db"):
        os.remove("./test_hotfixes.db")

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
def admin_client(db_session):
    provider = LocalAuthProvider()
    admin = User(
        username="admin_hotfix",
        email_or_login="admin_hotfix@cfms.local",
        password_hash=provider.hash_password("adminpass"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    c = TestClient(app)
    c.post("/auth/login", data={"username": "admin_hotfix", "password": "adminpass"})
    yield c
    app.dependency_overrides.clear()

def test_audit_log_viewer_endpoint(admin_client):
    res = admin_client.get("/admin/audit")
    assert res.status_code == 200
    assert "Журнал аудита" in res.text

def test_unauthenticated_html_redirect(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    c = TestClient(app)
    res = c.get("/admin/dashboard", headers={"accept": "text/html"}, follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/auth/login"
    app.dependency_overrides.clear()

def test_admin_dashboard_auth_by_username_and_email(db_session):
    provider = LocalAuthProvider()
    admin = User(
        username="admin_dash_test",
        email_or_login="admin_dash_test@cfms.local",
        password_hash=provider.hash_password("admin123"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db

    # Test client 1: Login by username
    client1 = TestClient(app)
    res1 = client1.post("/auth/login", data={"username": "admin_dash_test", "password": "admin123"}, follow_redirects=False)
    assert res1.status_code == 302
    session_cookie1 = res1.cookies.get("session")

    client1.cookies.set("session", session_cookie1)
    dash1 = client1.get("/admin/dashboard")
    assert dash1.status_code == 200
    assert "Панель администратора" in dash1.text

    # Test client 2: Login by email
    client2 = TestClient(app)
    res2 = client2.post("/auth/login", data={"username": "admin_dash_test@cfms.local", "password": "admin123"}, follow_redirects=False)
    assert res2.status_code == 302
    session_cookie2 = res2.cookies.get("session")

    client2.cookies.set("session", session_cookie2)
    dash2 = client2.get("/admin/dashboard")
    assert dash2.status_code == 200
    assert "Панель администратора" in dash2.text

    app.dependency_overrides.clear()

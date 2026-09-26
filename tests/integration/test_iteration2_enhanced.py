import io
import os

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.providers import LocalAuthProvider
from app.core.database import Base, get_db
from app.main import app
from app.models.models import AuditLog, User, UserRole

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_iteration2_full.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_iteration2_full.db"):
        os.remove("./test_iteration2_full.db")


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
        username="admin_i2_test",
        email_or_login="admin_i2_test@cfms.local",
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
    c.post("/auth/login", data={"username": "admin_i2_test", "password": "adminpass"})
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def user_client(db_session):
    provider = LocalAuthProvider()
    user = User(
        username="regular_user",
        email_or_login="user@cfms.local",
        password_hash=provider.hash_password("userpass"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    c = TestClient(app)
    c.post("/auth/login", data={"username": "regular_user", "password": "userpass"})
    yield c
    app.dependency_overrides.clear()


def test_rbac_admin_routes_blocked_for_regular_user(user_client):
    res = user_client.get("/admin/users")
    assert res.status_code == 403

    res_comp = user_client.get("/admin/computers")
    assert res_comp.status_code == 403


def test_user_crud_and_password_reset(admin_client, db_session):
    # Create User
    resp = admin_client.post(
        "/admin/users/create",
        data={
            "username": "tech_mary",
            "email_or_login": "mary@cfms.local",
            "password": "techpassword123",
            "role": "TECHNICIAN",
            "is_active": "true",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    created_user = db_session.query(User).filter(User.username == "tech_mary").first()
    assert created_user is not None

    # Reset Password
    reset_resp = admin_client.post(
        f"/admin/users/{created_user.id}/reset-password", data={"new_password": "newpassword999"}, follow_redirects=True
    )
    assert reset_resp.status_code == 200

    provider = LocalAuthProvider()
    db_session.refresh(created_user)
    assert provider.verify_password("newpassword999", created_user.password_hash)

    # Audit log check
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "reset_password", AuditLog.entity_id == created_user.id)
        .first()
    )
    assert audit is not None


def test_user_role_update_persistence(admin_client, db_session):
    # Create user as USER
    provider = LocalAuthProvider()
    target_user = User(
        username="role_change_user",
        email_or_login="role_change@cfms.local",
        password_hash=provider.hash_password("password123"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add(target_user)
    db_session.commit()
    db_session.refresh(target_user)

    # Edit user role to TECHNICIAN
    resp = admin_client.post(
        f"/admin/users/{target_user.id}/edit",
        data={
            "username": "role_change_user",
            "email_or_login": "role_change@cfms.local",
            "role": "technician",
            "is_active": "true",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    db_session.refresh(target_user)
    assert target_user.role == UserRole.TECHNICIAN

    # Edit user role to ADMIN
    resp_admin = admin_client.post(
        f"/admin/users/{target_user.id}/edit",
        data={
            "username": "role_change_user",
            "email_or_login": "role_change@cfms.local",
            "role": "ADMIN",
            "is_active": "true",
        },
        follow_redirects=True,
    )
    assert resp_admin.status_code == 200

    db_session.refresh(target_user)
    assert target_user.role == UserRole.ADMIN


def test_computer_validation_errors(admin_client):
    # Bad IP address
    resp = admin_client.post(
        "/admin/computers/create",
        data={
            "hostname": "BAD-IP-PC",
            "ip": "999.999.999.999",
            "mac": "00:11:22:33:44:55",
        },
    )
    assert resp.status_code == 400
    assert "Некорректный IP-адрес" in resp.text

    # Bad MAC address
    resp_mac = admin_client.post(
        "/admin/computers/create",
        data={
            "hostname": "BAD-MAC-PC",
            "ip": "192.168.1.10",
            "mac": "invalid-mac",
        },
    )
    assert resp_mac.status_code == 400
    assert "Некорректный MAC-адрес" in resp_mac.text


def test_excel_import_template_download(admin_client):
    resp = admin_client.get("/admin/import/template")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_excel_import_hard_error_blocking(admin_client):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["hostname", "ip", "mac", "os", "location", "owner", "is_round_the_clock"])
    # Row with bad IP and missing hostname
    ws.append(["", "999.999.999.999", "00:11:22:33:44:55", "Ubuntu", "Room 1", "admin", "нет"])

    file_stream = io.BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)

    response = admin_client.post(
        "/admin/import/preview",
        files={
            "file": (
                "invalid_fleet.xlsx",
                file_stream.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200
    assert "Импорт заблокирован" in response.text or "Отсутствует hostname" in response.text

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
from app.models.models import AuditLog, Computer, User, UserRole

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_iteration2.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_iteration2.db"):
        os.remove("./test_iteration2.db")

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
        username="admin_i2",
        email_or_login="admin_i2@cfms.local",
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
    # Login as admin
    c.post("/auth/login", data={"username": "admin_i2", "password": "adminpass"})
    yield c
    app.dependency_overrides.clear()

def test_user_crud_and_audit(admin_client, db_session):
    # Create User
    resp = admin_client.post(
        "/admin/users/create",
        data={
            "username": "tech_john",
            "email_or_login": "john@cfms.local",
            "password": "techpassword123",
            "role": "TECHNICIAN",
            "is_active": "true",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    created_user = db_session.query(User).filter(User.username == "tech_john").first()
    assert created_user is not None
    assert created_user.role == UserRole.TECHNICIAN

    # Verify audit log created
    audit = db_session.query(AuditLog).filter(AuditLog.action == "create_user", AuditLog.entity_id == created_user.id).first()
    assert audit is not None
    assert audit.after_json["username"] == "tech_john"

    # Update User
    resp_update = admin_client.post(
        f"/admin/users/{created_user.id}/edit",
        data={
            "username": "tech_john_updated",
            "email_or_login": "john@cfms.local",
            "role": "TECHNICIAN",
            "is_active": "true",
        },
        follow_redirects=True,
    )
    assert resp_update.status_code == 200
    db_session.refresh(created_user)
    assert created_user.username == "tech_john_updated"

def test_computer_crud_and_audit(admin_client, db_session):
    # Create Computer
    resp = admin_client.post(
        "/admin/computers/create",
        data={
            "hostname": "PC-SERVER-01",
            "ip": "192.168.1.100",
            "mac": "00:11:22:33:44:55",
            "os": "Windows 11",
            "location": "Room 101",
            "is_round_the_clock": "true",
            "notes": "Main domain controller",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    comp = db_session.query(Computer).filter(Computer.hostname == "PC-SERVER-01").first()
    assert comp is not None
    assert comp.is_round_the_clock is True

    # Audit log check
    audit = db_session.query(AuditLog).filter(AuditLog.action == "create_computer", AuditLog.entity_id == comp.id).first()
    assert audit is not None

    # Delete Computer
    del_resp = admin_client.post(f"/admin/computers/{comp.id}/delete", follow_redirects=True)
    assert del_resp.status_code == 200
    deleted_comp = db_session.query(Computer).filter(Computer.id == comp.id).first()
    assert deleted_comp is None

def test_excel_import_preview_and_confirm(admin_client, db_session):
    # Create a mock openpyxl workbook in memory
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["hostname", "ip", "mac", "os", "location", "owner", "is_round_the_clock"])
    ws.append(["MOCK-PC-01", "10.0.0.1", "AA:BB:CC:DD:EE:FF", "Ubuntu 22.04", "Server Room", "admin_i2", "да"])
    ws.append(["MOCK-PC-02", "10.0.0.2", "AA:BB:CC:DD:EE:FE", "Windows 10", "Room 202", "unknown_user", "нет"])

    file_stream = io.BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)

    # Upload for preview
    response = admin_client.post(
        "/admin/import/preview",
        files={"file": ("test_fleet.xlsx", file_stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200
    assert "MOCK-PC-01" in response.text
    assert "MOCK-PC-02" in response.text

    # Extract file_token from HTML form response
    import re
    match = re.search(r'name="file_token"\s+value="([^"]+)"', response.text)
    assert match is not None
    file_token = match.group(1)

    # Confirm import
    confirm_resp = admin_client.post(
        "/admin/import/confirm",
        data={"file_token": file_token},
        follow_redirects=True,
    )
    assert confirm_resp.status_code == 200

    # Verify computers imported into DB
    pc1 = db_session.query(Computer).filter(Computer.hostname == "MOCK-PC-01").first()
    assert pc1 is not None
    assert pc1.is_round_the_clock is True

    pc2 = db_session.query(Computer).filter(Computer.hostname == "MOCK-PC-02").first()
    assert pc2 is not None
    assert pc2.is_round_the_clock is False

    # Audit log check
    audit = db_session.query(AuditLog).filter(AuditLog.action == "excel_import_fleet").first()
    assert audit is not None
    assert audit.after_json["imported_count"] == 2

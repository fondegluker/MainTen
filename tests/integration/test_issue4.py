"""Regression tests for Issue 4: Protocol Editor."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_session_cookie
from app.core.database import Base, get_db
from app.main import app
from app.models.models import (
    AuditLog,
    MaintenanceEvent,
    MaintenanceEventCheck,
    MaintenanceEventStatus,
    MaintenanceProtocolItem,
    User,
    UserRole,
)

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_issue4.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_issue4.db"):
        os.remove("./test_issue4.db")


@pytest.fixture
def db_session(setup_db):
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


def test_protocol_editor_crud_reorder_and_reference_safety(db_session: Session):
    provider = LocalAuthProvider()
    admin = User(
        username="admin_i4",
        email_or_login="admin_i4@example.com",
        password_hash=provider.hash_password("adminpass"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    user = User(
        username="user_i4",
        email_or_login="user_i4@example.com",
        password_hash=provider.hash_password("userpass"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add_all([admin, user])
    db_session.commit()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app, follow_redirects=False)

    # 1. Non-admin -> 403
    client.cookies.set("session", generate_session_cookie(user.id))
    assert client.get("/admin/protocol").status_code == 403

    # 2. Admin -> 200
    client.cookies.set("session", generate_session_cookie(admin.id))
    assert client.get("/admin/protocol").status_code == 200

    # 3. Create protocol item -> 302
    res_create = client.post(
        "/admin/protocol/create",
        data={"title_ru": "Проверка кабелей", "title_en": "Check cables", "is_active": "on"},
    )
    assert res_create.status_code == 302

    item = db_session.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.title_en == "Check cables").first()
    assert item is not None
    assert item.order_index == 0

    # 4. Create second item
    client.post(
        "/admin/protocol/create",
        data={"title_ru": "Очистка пыли", "title_en": "Clean dust", "is_active": "on"},
    )
    item2 = db_session.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.title_en == "Clean dust").first()
    assert item2 is not None

    # 5. Delete unreferenced item2 -> succeeds
    res_del_unref = client.post(f"/admin/protocol/{item2.id}/delete")
    assert res_del_unref.status_code == 302
    assert db_session.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.id == item2.id).first() is None

    # 6. Reference item in a MaintenanceEventCheck
    event = MaintenanceEvent(computer_id=1, status=MaintenanceEventStatus.DONE)
    db_session.add(event)
    db_session.flush()

    check = MaintenanceEventCheck(event_id=event.id, protocol_item_id=item.id, is_done=True)
    db_session.add(check)
    db_session.commit()

    # 7. Attempt delete referenced item -> 400 rejection
    res_del_ref = client.post(f"/admin/protocol/{item.id}/delete")
    assert res_del_ref.status_code == 400
    assert "деактивировать" in res_del_ref.text

    # 8. Toggle / deactivate item
    res_toggle = client.post(f"/admin/protocol/{item.id}/toggle")
    assert res_toggle.status_code == 302

    db_session.refresh(item)
    assert not item.is_active

    # Audit log entry check
    audit = db_session.query(AuditLog).filter(AuditLog.action == "toggle_protocol_item").first()
    assert audit is not None

    app.dependency_overrides.clear()

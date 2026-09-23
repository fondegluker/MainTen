"""Regression tests for Defect 3: RU/EN i18n locale persistence and query param priority."""

import os

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_session_cookie
from app.core.database import Base, get_db
from app.importer.template import build_template
from app.main import app
from app.models.models import User, UserRole

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_defect3.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_defect3.db"):
        os.remove("./test_defect3.db")


@pytest.fixture
def db_session(setup_db):
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


def test_query_param_locale_english(db_session: Session):
    client = TestClient(app)
    res = client.get("/auth/login?lang=en")
    assert res.status_code == 200
    assert "Computer Fleet Maintenance Scheduler" in res.text
    assert "Sign In" in res.text
    assert "Username or Email" in res.text
    assert "Система планирования ТО ПК" not in res.text


def test_cookie_locale_english(db_session: Session):
    client = TestClient(app)
    client.cookies.set("locale", "en")
    res = client.get("/auth/login")
    assert res.status_code == 200
    assert "Computer Fleet Maintenance Scheduler" in res.text
    assert "Sign In" in res.text


def test_authenticated_user_locale_switch_persists_to_db(db_session: Session):
    provider = LocalAuthProvider()
    user = User(
        username="usr_def3",
        email_or_login="usr_def3@example.com",
        password_hash=provider.hash_password("password123"),
        role=UserRole.USER,
        locale="ru",
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
    client = TestClient(app)
    session_cookie = generate_session_cookie(user.id)
    client.cookies.set("session", session_cookie)

    # Call /set-locale?locale=en
    res_switch = client.get("/set-locale?locale=en", follow_redirects=False)
    assert res_switch.status_code == 302

    # Verify user.locale updated in DB
    db_session.refresh(user)
    assert user.locale == "en"

    # Subsequent request without cookie or query param is English
    client.cookies.delete("locale")
    res_subsequent = client.get("/user/my-computers")
    assert res_subsequent.status_code == 200
    assert "My Computers" in res_subsequent.text

    app.dependency_overrides.clear()


def test_readme_sheet_is_bilingual():
    import io

    template_bytes = build_template()
    wb = openpyxl.load_workbook(filename=io.BytesIO(template_bytes))
    assert "Readme" in wb.sheetnames
    ws_readme = wb["Readme"]
    headers = [cell.value for cell in ws_readme[1]]
    assert "Column / Колонка" in headers
    assert "Description (RU)" in headers
    assert "Description (EN)" in headers

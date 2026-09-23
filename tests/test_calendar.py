import os
from datetime import date

import pytest
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command

TEST_DB_URL = "sqlite:///./test_calendar.db"
os.environ["DATABASE_URL"] = TEST_DB_URL

from app.models.models import DayKind, WorkingCalendar
from app.repositories.calendar_repository import CalendarRepository

engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def alembic_db():
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)

    # Run migration upgrade
    command.upgrade(alembic_cfg, "head")
    yield
    # Run migration downgrade
    command.downgrade(alembic_cfg, "base")
    if os.path.exists("./test_calendar.db"):
        os.remove("./test_calendar.db")


@pytest.fixture
def db_session(alembic_db):
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def test_calendar_seed_data(db_session):
    repo = CalendarRepository(db_session)

    # Check Jan 1, 2025 is New Year holiday
    jan1 = repo.get_day(date(2025, 1, 1))
    assert jan1 is not None
    assert jan1.is_working is False
    assert jan1.kind == DayKind.HOLIDAY
    assert jan1.description == "Новый год"

    # Check Jan 6, 2025 is regular workday
    jan6 = repo.get_day(date(2025, 1, 6))
    assert jan6 is not None
    assert jan6.is_working is True
    assert jan6.kind == DayKind.WORKDAY

    # Check Jan 4, 2025 is weekend
    jan4 = repo.get_day(date(2025, 1, 4))
    assert jan4 is not None
    assert jan4.is_working is False
    assert jan4.kind == DayKind.WEEKEND


def test_calendar_date_uniqueness(db_session):
    duplicate = WorkingCalendar(date=date(2025, 1, 1), is_working=True, kind=DayKind.WORKDAY, description="Duplicate")
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_calendar_repository_range(db_session):
    repo = CalendarRepository(db_session)
    # Range covering Jan 1 to Jan 10, 2025
    working_days = repo.get_working_days_range(date(2025, 1, 1), date(2025, 1, 10))
    # Jan 1, 2 holiday; Jan 3 Fri (work); Jan 4-5 Weekend; Jan 6-10 (6,8,9,10 work, Jan 7 holiday)
    working_dates = [d.date for d in working_days]
    assert date(2025, 1, 1) not in working_dates
    assert date(2025, 1, 2) not in working_dates
    assert date(2025, 1, 3) in working_dates
    assert date(2025, 1, 7) not in working_dates  # Orthodox Christmas
    assert date(2025, 1, 8) in working_dates

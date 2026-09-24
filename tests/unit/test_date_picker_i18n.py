"""Unit tests for localized weekday and date picker formatting (Issue 3)."""

from datetime import date
from sqlalchemy.orm import Session

from app.core.i18n import format_date_localized
from app.models.models import Computer
from app.services.scheduling_service import get_window_calendar_days


def test_format_date_localized_ru_and_en():
    """Test format_date_localized formats Russian and English weekday names correctly."""
    # 2025-05-02 is Friday (w_idx = 4)
    dt = date(2025, 5, 2)

    ru_str = format_date_localized(dt, locale="ru")
    assert ru_str == "02.05.2025 (Пт)"

    en_str = format_date_localized(dt, locale="en")
    assert en_str == "02.05.2025 (Fri)"


def test_window_calendar_days_i18n_formatting(db_session: Session, regular_user):
    """Test get_window_calendar_days formats dates using active locale."""
    comp = Computer(
        hostname="test-i18n-pc",
        ip="192.168.1.150",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2025, 5, 10),
    )
    db_session.add(comp)
    db_session.commit()

    ru_res = get_window_calendar_days(comp.id, db_session, today=date(2025, 5, 1), locale="ru")
    assert any("(Пн)" in d["formatted"] or "(Вт)" in d["formatted"] or "(Пт)" in d["formatted"] for d in ru_res["days"])
    assert not any("(Mon)" in d["formatted"] or "(Fri)" in d["formatted"] for d in ru_res["days"])

    en_res = get_window_calendar_days(comp.id, db_session, today=date(2025, 5, 1), locale="en")
    assert any("(Mon)" in d["formatted"] or "(Tue)" in d["formatted"] or "(Fri)" in d["formatted"] for d in en_res["days"])
    assert not any("(Пн)" in d["formatted"] or "(Пт)" in d["formatted"] for d in en_res["days"])

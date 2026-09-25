"""Integration tests for bulk calendar import template routes and importer validation (Issue 2)."""

from fastapi import status
from fastapi.testclient import TestClient

from app.auth.tokens import create_access_token


def test_download_calendar_templates_as_admin(client: TestClient, admin_user):
    """Test downloading CSV and JSON calendar import templates as ADMIN returns 200 and non-empty content."""
    token = create_access_token({"sub": str(admin_user.id)})
    headers = {"Cookie": f"access_token={token}"}

    # CSV template
    res_csv = client.get("/admin/calendar/import/template.csv", headers=headers)
    assert res_csv.status_code == status.HTTP_200_OK
    assert "text/csv" in res_csv.headers["content-type"]
    csv_text = res_csv.text
    assert "date,kind,is_working,description" in csv_text
    assert "2025-05-01,holiday" in csv_text

    # JSON template
    res_json = client.get("/admin/calendar/import/template.json", headers=headers)
    assert res_json.status_code == status.HTTP_200_OK
    assert "application/json" in res_json.headers["content-type"]
    json_data = res_json.json()
    assert isinstance(json_data, list)
    assert len(json_data) >= 1
    assert "date" in json_data[0]
    assert "kind" in json_data[0]


def test_bulk_import_parsed_templates_zero_errors(client: TestClient, admin_user):
    """Test uploading generated templates to bulk-import endpoint succeeds with zero errors."""
    token = create_access_token({"sub": str(admin_user.id)})
    headers = {"Cookie": f"access_token={token}"}

    # Download CSV template
    res_csv = client.get("/admin/calendar/import/template.csv", headers=headers)
    csv_bytes = res_csv.content

    # Upload CSV template
    upload_res = client.post(
        "/admin/calendar/bulk-import",
        headers=headers,
        files={"file": ("calendar_template.csv", csv_bytes, "text/csv")},
        follow_redirects=False,
    )
    assert upload_res.status_code == status.HTTP_302_FOUND
    assert "message=Импортировано" in upload_res.headers["location"]


def test_download_calendar_templates_as_non_admin(client: TestClient, regular_user):
    """Test downloading calendar import templates as non-admin (USER) returns 403 Forbidden."""
    token = create_access_token({"sub": str(regular_user.id)})
    headers = {"Cookie": f"access_token={token}"}

    res_csv = client.get("/admin/calendar/import/template.csv", headers=headers)
    assert res_csv.status_code == status.HTTP_403_FORBIDDEN

    res_json = client.get("/admin/calendar/import/template.json", headers=headers)
    assert res_json.status_code == status.HTTP_403_FORBIDDEN

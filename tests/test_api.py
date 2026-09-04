"""Tests for the FastAPI endpoints."""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

# Build a sample DMARC XML for testing
SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8" ?>
<feedback>
  <report_metadata>
    <org_name>test-org</org_name>
    <email>test@example.com</email>
    <report_id>test-api-001</report_id>
    <date_range>
      <begin>1788307200</begin>
      <end>1788393599</end>
    </date_range>
  </report_metadata>
  <policy_published>
    <domain>example.com</domain>
    <adkim>r</adkim>
    <aspf>r</aspf>
    <p>none</p>
    <sp>none</sp>
    <pct>100</pct>
  </policy_published>
  <record>
    <row>
      <source_ip>1.2.3.4</source_ip>
      <count>10</count>
      <policy_evaluated>
        <disposition>none</disposition>
        <dkim>pass</dkim>
        <spf>pass</spf>
      </policy_evaluated>
    </row>
    <identifiers>
      <header_from>example.com</header_from>
    </identifiers>
    <auth_results>
      <dkim><domain>example.com</domain><result>pass</result></dkim>
      <spf><domain>example.com</domain><result>pass</result></spf>
    </auth_results>
  </record>
</feedback>
"""


@pytest.fixture
def client(tmp_path):
    """Create test client with temp directories."""
    import os

    os.environ["DMARC_REPORTS_DIR"] = str(tmp_path / "reports")
    os.environ["DMARC_DATABASE_URL"] = "sqlite+aiosqlite:///test.db"

    # Re-import to pick up new env
    from api.main import app

    return TestClient(app)


def _make_zip(xml_bytes: bytes, name: str = "test.xml") -> bytes:
    """Wrap XML bytes in a zip archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, xml_bytes)
    return buf.getvalue()


def test_health_endpoint(client: TestClient) -> None:
    """Health check returns 200."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_upload_xml(client: TestClient) -> None:
    """Uploading a plain XML file succeeds."""
    response = client.post(
        "/api/upload",
        files={"file": ("report.xml", SAMPLE_XML, "application/xml")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ingested"
    assert "report.xml" in data["extracted_files"]


def test_upload_zip(client: TestClient) -> None:
    """Uploading a zip with one XML succeeds."""
    zip_bytes = _make_zip(SAMPLE_XML)
    response = client.post(
        "/api/upload",
        files={"file": ("report.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ingested"
    assert len(data["per_file_analysis"]) == 1


def test_upload_rejects_bad_extension(client: TestClient) -> None:
    """Uploading a .exe is rejected."""
    response = client.post(
        "/api/upload",
        files={"file": ("malware.exe", b"bad", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_upload_rejects_empty_file(client: TestClient) -> None:
    """Uploading an empty file is rejected."""
    response = client.post(
        "/api/upload",
        files={"file": ("empty.xml", b"", "application/xml")},
    )
    assert response.status_code == 400


def test_list_reports(client: TestClient) -> None:
    """After upload, reports endpoint returns the report."""
    # First upload
    client.post(
        "/api/upload",
        files={"file": ("report.xml", SAMPLE_XML, "application/xml")},
    )

    # Then list
    response = client.get("/api/reports")
    assert response.status_code == 200
    reports = response.json()
    assert len(reports) >= 1
    assert reports[0]["domain"] == "example.com"


def test_get_report_detail(client: TestClient) -> None:
    """Detail endpoint returns full record data."""
    # Upload first
    upload_resp = client.post(
        "/api/upload",
        files={"file": ("report.xml", SAMPLE_XML, "application/xml")},
    )
    report_id = upload_resp.json()["per_file_analysis"][0]["report_id"]

    # Get detail
    response = client.get(f"/api/reports/{report_id}/detail")
    assert response.status_code == 200
    data = response.json()
    assert data["report"]["org_name"] == "test-org"
    assert len(data["records"]) == 1
    assert data["records"][0]["source_ip"] == "1.2.3.4"
    assert data["records"][0]["dkim_auth"][0]["result"] == "pass"

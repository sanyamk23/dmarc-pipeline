"""Tests for the DMARC XML parser."""

from __future__ import annotations

import gzip
import io
import zipfile

import pytest

from parsers.dmarc_xml import parse_dmarc_xml

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8" ?>
<feedback>
  <version>1.0</version>
  <report_metadata>
    <org_name>google.com</org_name>
    <email>noreply-dmarc-support@google.com</email>
    <report_id>test-report-123</report_id>
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
      <source_ip>203.0.113.1</source_ip>
      <count>5</count>
      <policy_evaluated>
        <disposition>none</disposition>
        <dkim>pass</dkim>
        <spf>pass</spf>
      </policy_evaluated>
    </row>
    <identifiers>
      <header_from>example.com</header_from>
      <envelope_from>example.com</envelope_from>
    </identifiers>
    <auth_results>
      <dkim>
        <domain>example.com</domain>
        <result>pass</result>
        <selector>google</selector>
      </dkim>
      <spf>
        <domain>example.com</domain>
        <result>pass</result>
        <scope>mfrom</scope>
      </spf>
    </auth_results>
  </record>
  <record>
    <row>
      <source_ip>198.51.100.1</source_ip>
      <count>2</count>
      <policy_evaluated>
        <disposition>reject</disposition>
        <dkim>fail</dkim>
        <spf>fail</spf>
      </policy_evaluated>
    </row>
    <identifiers>
      <header_from>example.com</header_from>
    </identifiers>
    <auth_results>
      <dkim>
        <domain>example.com</domain>
        <result>fail</result>
      </dkim>
      <spf>
        <domain>example.com</domain>
        <result>none</domain>
      </spf>
    </auth_results>
  </record>
</feedback>
"""


def test_parse_basic_report() -> None:
    """Parser extracts metadata, policy, and records correctly."""
    report = parse_dmarc_xml("test.xml", SAMPLE_XML)

    assert report.metadata.org_name == "google.com"
    assert report.metadata.report_id == "test-report-123"
    assert report.metadata.policy.domain == "example.com"
    assert report.metadata.policy.adkim == "r"
    assert report.metadata.policy.p == "none"
    assert len(report.records) == 2


def test_parse_first_record() -> None:
    """First record passes both DKIM and SPF."""
    report = parse_dmarc_xml("test.xml", SAMPLE_XML)
    rec = report.records[0]

    assert rec.source_ip == "203.0.113.1"
    assert rec.count == 5
    assert rec.dkim_aligned is True
    assert rec.spf_aligned is True
    assert rec.dkim_result == "pass"
    assert rec.spf_result == "pass"
    assert rec.dkim_auth[0].selector == "google"
    assert rec.spf_auth[0].scope == "mfrom"


def test_parse_second_record() -> None:
    """Second record fails both checks."""
    report = parse_dmarc_xml("test.xml", SAMPLE_XML)
    rec = report.records[1]

    assert rec.source_ip == "198.51.100.1"
    assert rec.count == 2
    assert rec.dkim_aligned is False
    assert rec.spf_aligned is False
    assert rec.disposition == "reject"


def test_parse_gzipped_xml() -> None:
    """Parser transparently decompresses gzip payloads."""
    gzipped = gzip.compress(SAMPLE_XML)
    report = parse_dmarc_xml("test.xml.gz", gzipped)

    assert report.metadata.org_name == "google.com"
    assert len(report.records) == 2


def test_parse_invalid_xml_raises() -> None:
    """Parser raises ValueError on malformed XML."""
    with pytest.raises(ValueError, match="Invalid XML"):
        parse_dmarc_xml("bad.xml", b"<not valid xml")


def test_parse_empty_xml_raises() -> None:
    """Parser raises ValueError on empty input."""
    with pytest.raises(ValueError):
        parse_dmarc_xml("empty.xml", b"")

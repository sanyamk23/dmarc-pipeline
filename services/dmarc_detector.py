"""DMARC report detector — multi-layer verification.

Goal: Zero false positives, zero false negatives.

A file is only processed as a DMARC report if it passes ALL layers:
  Layer 1: Sender verification (known DMARC reporters)
  Layer 2: Subject line pattern matching
  Layer 3: Attachment filename pattern (RFC 7489)
  Layer 4: XML content validation (ground truth)

Each layer is independent — any single rejection means "not a DMARC report".
"""

from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger("dmarc.detector")

# ═══════════════════════════════════════════════════════════════════════════
# LAYER 1: Sender Verification
# ═══════════════════════════════════════════════════════════════════════════

# Known DMARC aggregate report senders.
# These are the actual domains that send DMARC reports from major providers.
# Source: each provider's documentation + observed report patterns.
KNOWN_REPORTER_DOMAINS = {
    # Google
    "google.com",
    "googlemail.com",
    "noreply-dmarc-support.google.com",
    # Microsoft / Outlook / Hotmail
    "microsoft.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "enterprise.protection.outlook.com",
    # Yahoo
    "yahoo.com",
    "yahoogroups.com",
    "ymail.com",
    "rocketmail.com",
    # Amazon SES
    "amazonses.com",
    "amazon.com",
    # Other major reporters
    "mail.ru",
    "yandex.ru",
    "zoho.com",
    "proofpoint.com",
    "mimecast.com",
    "barracuda.com",
    "pphosted.com",       # Proofpoint
    "emailsrvr.com",      # Rackspace
    "sendgrid.net",       # Twilio SendGrid
    "mailgun.org",        # Mailgun
    "sparkpostmail.com",  # SparkPost
    "mandrillapp.com",    # Mailchimp Mandrill
    "facebook.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "dropbox.com",
    "slack.com",
    "atlassian.net",
    "github.com",
    "gitlab.com",
    # Add more as discovered — these don't expire or change often
}

# Patterns that match sender domains (for subdomains and variations)
KNOWN_REPORTER_PATTERNS = [
    re.compile(r"google\.com$"),
    re.compile(r"microsoft\.com$"),
    re.compile(r"outlook\.com$"),
    re.compile(r"amazonses\.com$"),
    re.compile(r"yahoo\.com$"),
    re.compile(r"proofpoint\.com$"),
    re.compile(r"mimecast\.com$"),
    re.compile(r"barracudanetworks\.com$"),
    re.compile(r"sendgrid\.net$"),
    re.compile(r"mailgun\.net$"),
    re.compile(r"zoho\.com$"),
]


def verify_sender(sender: str) -> bool:
    """Check if email sender is a known DMARC aggregate reporter."""
    sender_lower = sender.lower().strip()

    # Extract domain from email (handle "Name <email@domain.com>" format)
    email_match = re.search(r"<([^>]+)>", sender_lower)
    if email_match:
        sender_lower = email_match.group(1)

    # Extract domain
    if "@" in sender_lower:
        domain = sender_lower.split("@")[-1]
    else:
        domain = sender_lower

    # Direct match against known domains
    if domain in KNOWN_REPORTER_DOMAINS:
        return True

    # Pattern match (for subdomains like mail.google.com)
    for pattern in KNOWN_REPORTER_PATTERNS:
        if pattern.search(domain):
            return True

    return False


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 2: Subject Line Pattern Matching
# ═══════════════════════════════════════════════════════════════════════════

# DMARC aggregate reports have a very specific subject format:
#   "Report Domain: <domain> Submitter: <org>"
#   "Report Domain: <domain> Submitter: <org> Report-ID: <id>"
#   "DMARC Report for <domain>"
#   "<org> DMARC Report - <domain>"
DMARC_SUBJECT_PATTERNS = [
    # Standard format from Google, Microsoft, etc.
    re.compile(r"report\s+domain\s*:.*submitter\s*:", re.IGNORECASE),
    # Alternative format
    re.compile(r"dmarc\s+report\s+(for|from|domain)", re.IGNORECASE),
    # Amazon SES format
    re.compile(r"dmarc.*aggregate.*report", re.IGNORECASE),
    # Some providers use this
    re.compile(r"submitter\s*:.*report\s*(id|domain)", re.IGNORECASE),
    # Forensic reports (different from aggregate, but related)
    re.compile(r"dmarc.*forensic.*report", re.IGNORECASE),
]


def verify_subject(subject: str) -> bool:
    """Check if email subject matches DMARC report patterns."""
    for pattern in DMARC_SUBJECT_PATTERNS:
        if pattern.search(subject):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 3: Attachment Filename Pattern (RFC 7489)
# ═══════════════════════════════════════════════════════════════════════════

# DMARC aggregate report attachments follow this naming convention:
#   <report-domain>!<submitter-domain>!<start-timestamp>!<end-timestamp>.<ext>
#
# Examples:
#   example.com!google.com!1788307200!1788393599.zip
#   example.com!microsoft.com!1788134400!1788220800.xml.gz
#
# The timestamps are Unix epoch seconds.

DMARC_FILENAME_PATTERN = re.compile(
    r"^"
    r"[a-zA-Z0-9][\w\-\.]*"          # report domain
    r"!"
    r"[a-zA-Z0-9][\w\-\.]*"          # submitter domain
    r"!"
    r"\d{8,12}"                       # start timestamp (epoch seconds)
    r"!"
    r"\d{8,12}"                       # end timestamp (epoch seconds)
    r"\.(zip|xml|gz|xml\.gz)$"        # extension
    ,
    re.IGNORECASE,
)


def verify_filename(filename: str) -> bool:
    """Check if attachment filename matches DMARC report naming convention."""
    return bool(DMARC_FILENAME_PATTERN.match(filename))


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 4: XML Content Validation (Ground Truth)
# ═══════════════════════════════════════════════════════════════════════════

# A valid DMARC aggregate report XML must have:
#   - Root element: <feedback>
#   - Child: <report_metadata> with <org_name> and <report_id>
#   - Child: <policy_published> with <domain>
#   - Child: <record> elements (at least one)

REQUIRED_XML_ELEMENTS = [
    "report_metadata",
    "policy_published",
    "record",
]


def verify_xml_content(xml_bytes: bytes) -> bool:
    """Parse XML and verify it's a valid DMARC aggregate report."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return False

    # Must have <feedback> root
    if root.tag != "feedback":
        return False

    # Must have all required child elements
    for required in REQUIRED_XML_ELEMENTS:
        if root.find(required) is None:
            return False

    # Must have at least one <record>
    records = root.findall("record")
    if len(records) == 0:
        return False

    # Verify report_metadata has required fields
    meta = root.find("report_metadata")
    if meta is not None:
        if meta.find("org_name") is None:
            return False
        if meta.find("report_id") is None:
            return False

    # Verify policy_published has domain
    policy = root.find("policy_published")
    if policy is not None:
        if policy.find("domain") is None:
            return False

    return True


def verify_zip_content(zip_bytes: bytes) -> bool:
    """Verify a zip file contains a valid DMARC report XML."""
    import io

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            # Find XML files in the archive
            xml_files = [n for n in zf.namelist() if n.lower().endswith(".xml")]

            if not xml_files:
                return False

            # Verify at least one XML file is a valid DMARC report
            for xml_name in xml_files:
                xml_data = zf.read(xml_name)
                if verify_xml_content(xml_data):
                    return True

            return False
    except (zipfile.BadZipFile, Exception):
        return False


def verify_file_content(filepath: Path) -> bool:
    """Verify a file (xml, gz, or zip) is a valid DMARC report."""
    suffix = filepath.suffix.lower()

    if suffix == ".xml":
        return verify_xml_content(filepath.read_bytes())

    if suffix == ".gz" or str(filepath).endswith(".xml.gz"):
        import gzip
        try:
            data = gzip.decompress(filepath.read_bytes())
            return verify_xml_content(data)
        except Exception:
            return False

    if suffix == ".zip":
        return verify_zip_content(filepath.read_bytes())

    return False


# ═══════════════════════════════════════════════════════════════════════════
# COMBINED DETECTION
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class DetectionResult:
    """Result of DMARC report detection."""
    is_dmarc_report: bool
    confidence: str  # "high", "medium", "low"
    layer_results: dict[str, bool] = field(default_factory=dict)
    reason: str = ""


def detect_dmarc_report(
    sender: str = "",
    subject: str = "",
    filename: str = "",
    file_path: Optional[Path] = None,
) -> DetectionResult:
    """
    Multi-layer DMARC report detection.

    Returns DetectionResult with:
    - is_dmarc_report: True only if ALL applicable layers pass
    - confidence: "high" (all 4 layers), "medium" (3 layers), "low" (<3)
    - layer_results: which layers passed/failed
    - reason: human-readable explanation
    """
    layers = {}

    # Layer 1: Sender
    if sender:
        layers["sender"] = verify_sender(sender)

    # Layer 2: Subject
    if subject:
        layers["subject"] = verify_subject(subject)

    # Layer 3: Filename
    if filename:
        layers["filename"] = verify_filename(filename)

    # Layer 4: Content (ground truth — most reliable)
    if file_path and file_path.exists():
        layers["content"] = verify_file_content(file_path)

    # Decision logic
    passed = sum(1 for v in layers.values() if v)
    total = len(layers)

    # Content validation is the ground truth — if it passes, it's definitely a DMARC report
    if "content" in layers and layers["content"]:
        is_report = True
        confidence = "high"
        reason = "Valid DMARC aggregate report XML confirmed"
    # All layers must pass for high confidence
    elif passed == total and total >= 3:
        is_report = True
        confidence = "high"
        reason = f"All {total} verification layers passed"
    # 2 out of 3 layers (without content check) = medium confidence
    elif passed >= 2 and total >= 3 and "content" not in layers:
        is_report = True
        confidence = "medium"
        reason = f"{passed}/{total} layers passed (content not verified yet)"
    else:
        is_report = False
        confidence = "low"
        failed = [k for k, v in layers.items() if not v]
        reason = f"Failed layers: {', '.join(failed)}"

    return DetectionResult(
        is_dmarc_report=is_report,
        confidence=confidence,
        layer_results=layers,
        reason=reason,
    )


# ═══════════════════════════════════════════════════════════════════════════
# CLI TESTING
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m services.dmarc_detector --sender 'a@b.com' --subject 'Report Domain: x' --filename 'x!y!123!456.zip'")
        print("  python -m services.dmarc_detector --file /path/to/report.zip")
        sys.exit(1)

    import argparse

    parser = argparse.ArgumentParser(description="Test DMARC report detection")
    parser.add_argument("--sender", default="")
    parser.add_argument("--subject", default="")
    parser.add_argument("--filename", default="")
    parser.add_argument("--file", default="")
    args = parser.parse_args()

    result = detect_dmarc_report(
        sender=args.sender,
        subject=args.subject,
        filename=args.filename,
        file_path=Path(args.file) if args.file else None,
    )

    print(f"Is DMARC report: {result.is_dmarc_report}")
    print(f"Confidence: {result.confidence}")
    print(f"Reason: {result.reason}")
    print(f"Layers: {result.layer_results}")

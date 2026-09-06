# DMARC Report Email Formats — Complete Reference

This document lists all known DMARC aggregate report email formats. The system searches broadly and validates content, so it catches all of these automatically.

---

## Major Providers

### Google (Gmail / Google Workspace)

**Sender:** `noreply-dmarc-support@google.com`
**Subject:** `Report Domain: example.com Submitter: google.com Report-ID: 1234567890`
**Attachment:** `example.com!google.com!1788307200!1788393599.zip`
**Notes:**
- Timestamps are Unix epoch seconds
- Always a `.zip` file containing one XML
- May contain multiple DKIM signatures (one for google.com, one for your domain)

### Microsoft (Outlook / Office 365 / Hotmail)

**Sender:** `dmarcreport@microsoft.com`
**Subject:** `Report Domain: example.com Submitter: microsoft.com`
**Attachment:** `example.com!microsoft.com!1788134400!1788220800.xml.gz`
**Notes:**
- May send `.xml.gz` instead of `.zip`
- Enterprise Protection uses: `enterprise.protection.outlook.com`

### Yahoo

**Sender:** `dmarcreports@yahoo.com`
**Subject:** `Yahoo! DMARC Report for example.com`
**Attachment:** `example.com!yahoo.com!1788307200!1788393599.zip`

### Amazon SES

**Sender:** `postmaster@amazonses.com`
**Subject:** `DMARC Report for example.com`
**Attachment:** `example.com!amazonses.com!1788307200!1788393599.zip`
**Notes:**
- Also sends failure/complaint notifications — we filter by content

---

## Email Providers

### Proofpoint

**Sender:** `dmarc-reports@proofpoint.com`
**Subject:** `DMARC Aggregate Report from Proofpoint`
**Attachment:** `example.com!proofpoint.com!1788307200!1788393599.zip`

### Mimecast

**Sender:** `dmarc@mimecast.com`
**Subject:** `DMARC Report - example.com`
**Attachment:** `example.com!mimecast.com!1788307200!1788393599.xml.gz`

### Barracuda

**Sender:** `dmarc@barracuda.com`
**Subject:** `Barracuda DMARC Report for example.com`
**Attachment:** `example.com!barracuda.com!1788307200!1788393599.zip`

### Rackspace

**Sender:** `dmarc@emailsrvr.com`
**Subject:** `DMARC Aggregate Report`
**Attachment:** `example.com!emailsrvr.com!1788307200!1788393599.zip`

### Zoho Mail

**Sender:** `dmarc@zoho.com`
**Subject:** `DMARC Report for example.com`
**Attachment:** `example.com!zoho.com!1788307200!1788393599.zip`

---

## Marketing Platforms

### SendGrid (Twilio)

**Sender:** `dmarc@sendgrid.net`
**Subject:** `SendGrid DMARC Report for example.com`
**Attachment:** `example.com!sendgrid.net!1788307200!1788393599.zip`

### Mailgun

**Sender:** `dmarc@mailgun.org`
**Subject:** `Mailgun DMARC Report`
**Attachment:** `example.com!mailgun.org!1788307200!1788393599.zip`

### SparkPost

**Sender:** `dmarc@sparkpostmail.com`
**Subject:** `SparkPost DMARC Aggregate Report`
**Attachment:** `example.com!sparkpostmail.com!1788307200!1788393599.zip`

### Mailchimp Mandrill

**Sender:** `dmarc@mandrillapp.com`
**Subject:** `Mandrill DMARC Report for example.com`
**Attachment:** `example.com!mandrillapp.com!1788307200!1788393599.zip`

---

## Social Media

### Facebook

**Sender:** `dmarc@facebook.com`
**Subject:** `Facebook DMARC Report for example.com`
**Attachment:** `example.com!facebook.com!1788307200!1788393599.zip`

### LinkedIn

**Sender:** `dmarc@linkedin.com`
**Subject:** `LinkedIn DMARC Report`
**Attachment:** `example.com!linkedin.com!1788307200!1788393599.zip`

### Twitter / X

**Sender:** `dmarc@x.com`
**Subject:** `X DMARC Report for example.com`
**Attachment:** `example.com!x.com!1788307200!1788393599.zip`

---

## SaaS Platforms

### Dropbox

**Sender:** `dmarc@dropbox.com`
**Subject:** `Dropbox DMARC Report`
**Attachment:** `example.com!dropbox.com!1788307200!1788393599.zip`

### Slack

**Sender:** `dmarc@slack.com`
**Subject:** `Slack DMARC Report for example.com`
**Attachment:** `example.com!slack.com!1788307200!1788393599.zip`

### Atlassian (Jira/Confluence)

**Sender:** `dmarc@atlassian.net`
**Subject:** `Atlassian DMARC Report`
**Attachment:** `example.com!atlassian.net!1788307200!1788393599.zip`

### GitHub

**Sender:** `dmarc@github.com`
**Subject:** `GitHub DMARC Report for example.com`
**Attachment:** `example.com!github.com!1788307200!1788393599.zip`

### GitLab

**Sender:** `dmarc@gitlab.com`
**Subject:** `GitLab DMARC Report`
**Attachment:** `example.com!gitlab.com!1788307200!1788393599.zip`

---

## Other Providers

### Mail.ru

**Sender:** `dmarc@mail.ru`
**Subject:** `Mail.ru DMARC Report for example.com`
**Attachment:** `example.com!mail.ru!1788307200!1788393599.zip`

### Yandex

**Sender:** `dmarc@yandex.ru`
**Subject:** `Yandex DMARC Report`
**Attachment:** `example.com!yandex.ru!1788307200!1788393599.zip`

---

## Attachment Naming Convention (RFC 7489)

All DMARC aggregate reports follow this naming pattern:

```
<report-domain>!<submitter-domain>!<start-timestamp>!<end-timestamp>.<ext>
```

**Examples:**
- `example.com!google.com!1788307200!1788393599.zip`
- `example.com!microsoft.com!1788134400!1788220800.xml.gz`
- `mydomain.org!yahoo.com!1788307200!1788393599.zip`

**Where:**
- `report-domain` = your domain
- `submitter-domain` = the entity sending the report
- `start-timestamp` = Unix epoch seconds (report period start)
- `end-timestamp` = Unix epoch seconds (report period end)
- `ext` = `zip`, `xml.gz`, or `xml`

---

## XML Structure (Content Validation)

The system validates the XML content to confirm it's a real DMARC report:

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<feedback>
  <version>1.0</version>
  <report_metadata>
    <org_name>google.com</org_name>
    <email>noreply-dmarc-support@google.com</email>
    <extra_contact_info>https://support.google.com/a/answer/2466580</extra_contact_info>
    <report_id>17550730322270491905</report_id>
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
      <source_ip>203.0.113.45</source_ip>
      <count>5</count>
      <policy_evaluated>
        <disposition>none</disposition>
        <dkim>pass</dkim>
        <spf>fail</spf>
      </policy_evaluated>
    </row>
    <identifiers>
      <header_from>example.com</header_from>
    </identifiers>
    <auth_results>
      <dkim>
        <domain>example.com</domain>
        <result>pass</result>
        <selector>google</selector>
      </dkim>
      <spf>
        <domain>example.com</domain>
        <result>none</result>
      </spf>
    </auth_results>
  </record>
</feedback>
```

**Required elements for validation:**
- Root: `<feedback>`
- `<report_metadata>` with `<org_name>` and `<report_id>`
- `<policy_published>` with `<domain>`
- At least one `<record>` element

---

## Testing Checklist

To validate your setup, send test emails to your connected Gmail account with:

- [ ] Subject containing "DMARC" and a `.zip` attachment
- [ ] Subject containing "Report Domain" and a `.xml.gz` attachment
- [ ] A real DMARC report forwarded from another email
- [ ] An attachment named `example.com!google.com!123456!123457.zip`

The system will:
1. Find the email (broad search)
2. Download the attachment
3. Validate XML content (Layer 4 — ground truth)
4. Process only valid DMARC reports
5. Log skipped attachments with reason

---

## Search Query Used

```
has:attachment newer_than:7d (dmarc OR "aggregate report" OR "Report Domain" OR "authentication report")
```

This catches ALL formats above, even ones not explicitly listed here.

---

## Troubleshooting

**If reports aren't being processed:**
1. Check Render logs for "No emails to check" — means search found nothing
2. Check logs for "Skipped: [filename]" — means content validation failed
3. Verify the email is in the connected Gmail's inbox (not archived)
4. Ensure the attachment is `.zip`, `.xml.gz`, or `.xml`

**Common false positives (correctly rejected):**
- PDFs with "DMARC" in subject
- Screenshots of DMARC reports
- Excel/CSV exports
- Password-protected zips

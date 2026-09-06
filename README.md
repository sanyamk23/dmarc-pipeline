# DMARC Report Pipeline

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/sanyamk23/dmarc-pipeline)

Automatically ingest, analyze, and browse DMARC aggregate reports. Set it up once and never think about it again.

## Deploy free (2 minutes)

1. Click the **Deploy to Render** button above
2. Or: create a **Web Service** on [render.com](https://render.com), connect this repo:

| Setting | Value |
|---------|-------|
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn wsgi:app -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT` |
| Plan | Free |

## Email automation (hands-free)

The app can watch your inbox and auto-ingest DMARC reports as they arrive.

### Option A: IMAP (any email provider)

Set these environment variables:

```bash
EMAIL_USER=your-email@gmail.com
EMAIL_PASSWORD=xxxx-xxxx-xxxx-xxxx  # Gmail App Password (not your real password!)
EMAIL_HOST=imap.gmail.com           # or imap-mail.outlook.com, etc.
EMAIL_SEARCH='SUBJECT "DMARC"'      # customize to match your reports
```

### Option B: Gmail API (more reliable)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create project → Enable Gmail API → Create OAuth credentials
3. Download `credentials.json` to the project root
4. Set: `GMAIL_CREDENTIALS_FILE=credentials.json`
5. First run opens browser for OAuth consent

### Run the watcher

```bash
# One-time check
python -m automation.email_watcher

# Continuous polling (every 5 min)
python -m automation.email_watcher --loop

# Or with Gmail API
python -m automation.gmail_api --loop
```

### On Render

Add to your start command:
```bash
python -m automation.email_watcher --loop & gunicorn wsgi:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT
```

## Persistent data (Supabase recommended)

### Setup Supabase (free, permanent)

1. Go to [supabase.com](https://supabase.com) → New Project
2. Run this SQL in **SQL Editor**:

```sql
CREATE TABLE dmarc_reports (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    xml_filename VARCHAR(255) NOT NULL,
    archive_filename VARCHAR(255),
    org_name VARCHAR(255),
    org_email VARCHAR(255),
    report_id VARCHAR(128) UNIQUE,
    date_begin TIMESTAMPTZ,
    date_end TIMESTAMPTZ,
    domain VARCHAR(255),
    adkim VARCHAR(8),
    aspf VARCHAR(8),
    p VARCHAR(16),
    sp VARCHAR(16),
    pct INTEGER DEFAULT 100,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE dmarc_records (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    report_id BIGINT REFERENCES dmarc_reports(id) ON DELETE CASCADE,
    source_ip VARCHAR(45),
    count INTEGER DEFAULT 0,
    header_from VARCHAR(255),
    envelope_from VARCHAR(255),
    envelope_to VARCHAR(255),
    disposition VARCHAR(16),
    dkim_aligned BOOLEAN DEFAULT FALSE,
    spf_aligned BOOLEAN DEFAULT FALSE,
    dkim_result VARCHAR(16),
    spf_result VARCHAR(16),
    dkim_domain VARCHAR(255),
    spf_domain VARCHAR(255),
    dkim_auth_json JSONB DEFAULT '[]'::jsonb,
    spf_auth_json JSONB DEFAULT '[]'::jsonb
);
```

3. In Render → Environment:
   - `DMARC_SUPABASE_URL` = `https://xxxxx.supabase.co`
   - `DMARC_SUPABASE_SERVICE_ROLE_KEY` = your service_role key

## Auto-sync (automatic email scanning)

The scheduler runs in the background and polls all connected accounts.

| Setting | Default | Description |
|---------|---------|-------------|
| `ENABLE_AUTO_SYNC` | `true` | Enable background polling |
| `AUTO_SYNC_INTERVAL` | `300` | Seconds between polls (5 min) |

### How it works

```
Every 5 minutes (default):
  1. Check all connected Gmail accounts
  2. For each account, search for unread emails with attachments
  3. Download attachments, verify content is valid DMARC XML
  4. Save valid reports to Supabase
  5. Track processed emails to avoid duplicates
```

### On Render

Update your **Start Command**:
```bash
python -m services.scheduler & gunicorn wsgi:app -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT
```

### Local development

```bash
./run.sh
```

Starts:
- Dashboard at http://localhost:8000
- Folder watcher (auto-ingest from `reports/` folder)
- Auto-sync scheduler (polls Gmail every 5 min)

## What it does

- **Email auto-ingestion** — watches inbox for DMARC reports, processes automatically
- **Folder watcher** — drop files in `reports/` for instant processing
- **Drag & drop upload** — zip, xml, or xml.gz
- **Multi-file zip support** — extracts and parses every XML inside
- **Per-file analysis** — health score, alignment stats, IP breakdown
- **Full detail view** — every parameter from every record
- **Collective analysis** — combined stats across all reports
- **Idempotent** — re-uploading is a safe no-op

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload` | Upload a report |
| `GET` | `/api/reports` | List reports |
| `GET` | `/api/reports/{id}/detail` | Full detail with every record |
| `GET` | `/api/reports/{id}/records` | Filterable records |
| `GET` | `/api/stats` | Aggregated statistics |
| `GET` | `/api/analysis` | Comprehensive analysis |
| `GET` | `/health` | Health check |

Interactive docs at `/docs`.

# DMARC Report Pipeline

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/sanyamk23/dmarc-pipeline)

Ingest, analyze, and browse DMARC aggregate reports. Drop a `.zip`, `.xml`, or
`.xml.gz` report and get a complete breakdown of your email authentication.

## Deploy free (2 minutes)

1. Click the **Deploy to Render** button above
2. Or: create a **Web Service** on [render.com](https://render.com), connect
   this repo, use these settings:

| Setting | Value |
|---------|-------|
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn wsgi:app -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT` |
| Plan | Free |

## Persistent data (optional, recommended)

By default the app uses SQLite (resets on deploy). For permanent storage that
survives deploys and can scale:

### Option A: Neon Postgres (free, recommended)

1. Go to [neon.tech](https://neon.tech) → sign up → create project
2. Copy the connection string (looks like `postgresql://user:pass@host/db`)
3. In Render dashboard → your service → **Environment** → add variable:
   - Key: `DMARC_DATABASE_URL`
   - Value: `postgresql+asyncpg://user:pass@host/db?sslmode=require`

### Option B: Render Postgres

1. In Render dashboard → **New** → **PostgreSQL** → Free plan
2. Create database, then link it to your web service
3. Render auto-sets the `DATABASE_URL` — add `DMARC_DATABASE_URL` pointing to it

## Local development

```bash
./run.sh
```

Opens at <http://localhost:8000>.

## What it does

- **Drag & drop upload** — zip, xml, or xml.gz
- **Multi-file zip support** — extracts and parses every XML inside
- **Folder watcher** — drop files in `reports/` for automatic ingestion
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

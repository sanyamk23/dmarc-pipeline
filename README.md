# DMARC Report Pipeline

A self-hosted pipeline + web application for ingesting, analyzing, and browsing
DMARC aggregate reports. Drop a `.zip`, `.xml`, or `.xml.gz` report and get a
complete breakdown of your email authentication health.

## Features

- **Folder watcher** — drop a file in `reports/` and it's ingested automatically
- **Web upload** — drag & drop on the dashboard
- **Multi-file zip support** — extracts and parses every XML in a zip
- **Per-file analysis** — health score, alignment stats, IP breakdown
- **Full detail view** — every parameter from every record, including all DKIM/SPF auth entries
- **Collective analysis** — combined view across all ingested reports
- **Idempotent** — re-uploading the same report is a safe no-op
- **SQLite storage** — zero external dependencies, async SQLAlchemy

## Quick start

```bash
./run.sh
```

Then open <http://localhost:8000>.

## Configuration

All settings are environment variables (prefix `DMARC_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DMARC_HOST` | `0.0.0.0` | Bind address |
| `DMARC_PORT` | `8000` | Bind port |
| `DMARC_DATABASE_URL` | `sqlite+aiosqlite:///./dmarc_reports.db` | Database connection |
| `DMARC_REPORTS_DIR` | `./reports` | Drop folder for incoming reports |
| `DMARC_MAX_UPLOAD_SIZE_MB` | `50` | Max upload size |
| `DMARC_WATCH_FOLDER` | `true` | Watch the drop folder |
| `DMARC_WORKER_COUNT` | `2` | Folder watcher workers |
| `DMARC_LOG_LEVEL` | `INFO` | Logging level |

Copy `.env.example` to `.env` to override locally.

## Docker

```bash
docker compose up --build
```

Or pull from GitHub Container Registry once pushed:

```bash
docker run -p 8000:8000 ghcr.io/sanyamk23/dmarc-pipeline:main
```

## CLI commands

```bash
python -m cli init-db          # create tables
python -m cli watch            # watch the drop folder
python -m cli ingest           # batch-ingest existing files
python -m cli serve            # run the API server
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload` | Upload a report (returns extracted files + analysis) |
| `GET` | `/api/reports` | List report envelopes |
| `GET` | `/api/reports/{id}` | Get a single report |
| `GET` | `/api/reports/{id}/detail` | Full detail: every field + every record |
| `GET` | `/api/reports/{id}/records` | List records (filter by `result=pass\|fail`) |
| `GET` | `/api/stats` | Aggregated statistics |
| `GET` | `/api/analysis` | Comprehensive analysis report |
| `GET` | `/health` | Liveness probe |

Interactive docs: <http://localhost:8000/docs> (Swagger UI)

## Deployment

### Render (free tier)

1. Push to GitHub
2. Create new **Web Service** on [render.com](https://render.com)
3. Connect your repo
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `gunicorn wsgi:app -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:10000`
6. Set environment variable: `DMARC_PORT=10000`

### Railway (free tier)

1. Push to GitHub
2. Create new project on [railway.app](https://railway.app)
3. Connect your repo
4. Railway auto-detects the Dockerfile

### Fly.io (free tier)

```bash
flyctl launch
flyctl deploy
```

## Project layout

```
dmarc_pipeline/
├── api/
│   └── main.py          # FastAPI app + endpoints
├── analysis/
│   └── engine.py        # Analysis report generator
├── models/
│   ├── database.py      # Async SQLAlchemy engine/session
│   └── schemas.py       # ORM models + Pydantic schemas
├── parsers/
│   └── dmarc_xml.py     # DMARC XML parser (RFC 7489)
├── workers/
│   ├── processor.py     # Unzip → parse → persist pipeline
│   └── watcher.py       # watchdog-based folder watcher
├── templates/           # Jinja2 templates
├── static/              # CSS + JS
├── reports/             # Drop folder (gitignored)
├── cli.py               # CLI entry point
├── wsgi.py              # Production entry point
├── run.sh               # Local dev runner
├── config.py            # Settings from environment
├── Dockerfile           # Production container
├── docker-compose.yml   # Local container orchestration
└── requirements.txt
```

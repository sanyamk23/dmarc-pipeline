# ═══════════════════════════════════════════════════════════════════════════
# DMARC Pipeline — production Dockerfile
# ═══════════════════════════════════════════════════════════════════════════

FROM python:3.12-slim AS base

WORKDIR /app

# ── System dependencies ──────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ──────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ─────────────────────────────────────────────────────────
COPY . .

# ── Non-root user ────────────────────────────────────────────────────────────
RUN adduser --disabled-password --gecos '' appuser && \
    mkdir -p /app/reports /app/quarantine && \
    chown -R appuser:appuser /app
USER appuser

# ── Runtime ──────────────────────────────────────────────────────────────────
EXPOSE 8000

ENV DMARC_HOST=0.0.0.0 \
    DMARC_PORT=8000 \
    PYTHONUNBUFFERED=1

# Use gunicorn with uvicorn workers for production
CMD ["gunicorn", "wsgi:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000"]

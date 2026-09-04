"""Production entry point — used by Gunicorn/Uvicorn in containers."""

import uvicorn

from config import settings

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )

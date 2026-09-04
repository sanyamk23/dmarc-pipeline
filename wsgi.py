"""Production entry point — used by Gunicorn on Render.

Gunicorn runs: gunicorn wsgi:app
So this module must expose `app` at the top level.
"""

import os
import sys

# Ensure the project root is on sys.path so `api`, `models`, etc. resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.main import app  # noqa: E402  (import after sys.path fix)

__all__ = ["app"]

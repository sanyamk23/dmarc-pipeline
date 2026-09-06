"""OAuth service — handles Gmail OAuth flow.

Flow:
1. User clicks "Connect Gmail" → redirect to Google consent screen
2. User authorizes → Google redirects back to /oauth/callback
3. We exchange code for tokens, fetch email, store in DB
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger("dmarc.oauth")

# ── Configuration ─────────────────────────────────────────────────────────────

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# Where Google redirects after authorization
# Override for production: https://your-domain.com/oauth/callback
REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:8000/oauth/callback")

# Scopes we need — READ ONLY, never send
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


# ── OAuth flow ────────────────────────────────────────────────────────────────


def get_authorization_url(state: str | None = None) -> str:
    """Build the Google OAuth authorization URL."""
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",       # Get refresh token
        "prompt": "consent",            # Force consent screen
        "state": state or secrets.token_urlsafe(32),
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """Exchange authorization code for tokens."""
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(GOOGLE_TOKEN_URL, data=data)

    if response.status_code != 200:
        raise RuntimeError(f"Token exchange failed: {response.text}")

    return response.json()


async def refresh_token(refresh_token: str) -> dict:
    """Refresh an expired access token."""
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(GOOGLE_TOKEN_URL, data=data)

    if response.status_code != 200:
        raise RuntimeError(f"Token refresh failed: {response.text}")

    return response.json()


async def get_email_from_token(access_token: str) -> str:
    """Fetch user's email from Google."""
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        response = await client.get(GOOGLE_USERINFO_URL, headers=headers)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch user info: {response.text}")

    return response.json().get("email", "")


# ── Token management ──────────────────────────────────────────────────────────


async def get_valid_access_token(token_json: dict) -> str:
    """Get a valid access token, refreshing if necessary."""
    from datetime import datetime, timedelta, timezone

    # Check if token is expired
    expires_at = token_json.get("expires_at")
    if expires_at:
        expiry = datetime.fromisoformat(expires_at)
        if datetime.now(timezone.utc) >= expiry:
            # Refresh
            new_token = await refresh_token(token_json["refresh_token"])
            token_json["access_token"] = new_token["access_token"]
            token_json["expires_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=new_token["expires_in"])
            ).isoformat()
            # Note: caller should persist updated token_json

    return token_json["access_token"]


# ── Client config for Gmail API ───────────────────────────────────────────────


def get_gmail_client_config() -> dict | None:
    """Get OAuth client config from environment."""
    if not CLIENT_ID or not CLIENT_SECRET:
        return None

    return {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }

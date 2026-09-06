"""Background scheduler — auto-syncs all connected accounts on a timer.

Runs as a background process alongside the web server.
Polls all connected Gmail accounts every N minutes.

Usage:
    python -m services.scheduler              # Poll every 5 min (default)
    python -m services.scheduler --interval 60  # Poll every 60 seconds
    python -m services.scheduler --once        # Run once and exit
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone

from models.accounts import list_accounts
from models.processed_emails import get_processed_count
from services.gmail_sync import sync_account_emails
from services.oauth import refresh_token

logger = logging.getLogger("dmarc.scheduler")

POLL_INTERVAL = int(os.environ.get("AUTO_SYNC_INTERVAL", "300"))  # 5 minutes default
BATCH_SIZE = 5  # Max accounts to sync per poll cycle


async def sync_all_accounts() -> dict:
    """Sync all active accounts. Returns summary."""
    accounts = list_accounts(active_only=True)

    if not accounts:
        return {"status": "no_accounts", "synced": 0}

    results = {
        "status": "ok",
        "accounts_checked": len(accounts),
        "total_reports": 0,
        "errors": [],
    }

    for account in accounts[:BATCH_SIZE]:
        account_id = account.get("id")
        email = account.get("email", "unknown")

        try:
            # Refresh token if needed
            token_json = account.get("token_json", {})
            if token_json.get("refresh_token"):
                expires_at = token_json.get("expires_at")
                if expires_at:
                    from datetime import datetime, timezone
                    expiry = datetime.fromisoformat(expires_at)
                    if datetime.now(timezone.utc) >= expiry:
                        new_token = await refresh_token(token_json["refresh_token"])
                        token_json["access_token"] = new_token["access_token"]
                        token_json["expires_at"] = (
                            datetime.now(timezone.utc)
                            + __import__("datetime").timedelta(seconds=new_token["expires_in"])
                        ).isoformat()
                        from models.accounts import update_token
                        update_token(account_id, token_json)

            # Sync emails
            count = await sync_account_emails(account)
            results["total_reports"] += count

            # Update last sync time
            from models.accounts import update_sync_time
            update_sync_time(account_id, datetime.now(timezone.utc).isoformat())

            logger.info("[%s] Auto-synced %d report(s)", email, count)

        except Exception as exc:
            logger.error("[%s] Sync failed: %s", email, exc)
            results["errors"].append({"email": email, "error": str(exc)})

    return results


async def run_loop() -> None:
    """Run continuous polling loop."""
    logger.info(
        "Auto-sync scheduler started (interval: %ds, max accounts: %d)",
        POLL_INTERVAL,
        BATCH_SIZE,
    )

    while True:
        try:
            start = time.time()
            results = await sync_all_accounts()
            elapsed = time.time() - start

            if results["status"] == "no_accounts":
                logger.debug("No accounts to sync")
            elif results["total_reports"] > 0:
                logger.info(
                    "Auto-sync complete: %d report(s) from %d account(s) in %.1fs",
                    results["total_reports"],
                    results["accounts_checked"],
                    elapsed,
                )
            else:
                logger.debug(
                    "Auto-sync: no new reports (%d accounts checked in %.1fs)",
                    results["accounts_checked"],
                    elapsed,
                )

        except Exception as exc:
            logger.error("Auto-sync cycle failed: %s", exc)

        await asyncio.sleep(POLL_INTERVAL)


def main():
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="DMARC Auto-Sync Scheduler")
    parser.add_argument(
        "--interval",
        type=int,
        default=POLL_INTERVAL,
        help=f"Poll interval in seconds (default: {POLL_INTERVAL})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit",
    )
    args = parser.parse_args()

    from logging_config import setup_logging
    setup_logging()

    global POLL_INTERVAL
    POLL_INTERVAL = args.interval

    if args.once:
        result = asyncio.run(sync_all_accounts())
        print(f"Synced {result['total_reports']} report(s) from {result['accounts_checked']} account(s)")
    else:
        logger.info("Starting auto-sync scheduler (Ctrl+C to stop)")
        try:
            asyncio.run(run_loop())
        except KeyboardInterrupt:
            logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()

from automation.email_watcher import run_once as check_email
from automation.gmail_api import run_once as check_gmail

__all__ = ["check_email", "check_gmail"]

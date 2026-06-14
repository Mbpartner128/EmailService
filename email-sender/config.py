# config.py — Edit before running
import os
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_APP_DIR = Path(__file__).resolve().parent
_load_env_file(_APP_DIR / ".env")

# ── SMTP ───────────────────────────────────────────────────────────────
SMTP_HOST     = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_SECURITY = os.environ.get("SMTP_SECURITY", "starttls").lower()  # none, starttls, tls, ssl
SMTP_USER     = os.environ.get("SMTP_USERNAME", os.environ.get("SMTP_USER", "your-email@gmail.com"))
SMTP_PASS     = os.environ.get("SMTP_PASSWORD", os.environ.get("SMTP_PASS", "xxxx xxxx xxxx xxxx"))
SMTP_FROM     = os.environ.get("SMTP_FROM", SMTP_USER)
SMTP_REPLY_TO = os.environ.get("SMTP_REPLY_TO", "")
SMTP_UNSUBSCRIBE_URL = os.environ.get("SMTP_UNSUBSCRIBE_URL", "")
SMTP_TIMEOUT_S = float(os.environ.get("SMTP_TIMEOUT", "20"))
SENDER_NAME   = os.environ.get("SMTP_SENDER_NAME", "Your Name / Company")

# ── Input file ──────────────────────────────────────────────────────────
INPUT_FILE   = "Brazil.xlsx"

# Sheet handling:
#   None     → process ALL sheets (all 6 states)
#   "Maranhão" → only that sheet
#   ["Maranhão", "Alagoas"] → specific sheets
TARGET_SHEETS = None

# ── Column names (as they appear in Brazil.xlsx) ────────────────────────
COL_NAME    = "Name"
COL_EMAIL   = "Email Address"
COL_STATUS  = "Status"              # e.g. "decline", "replied", "Scheduled"
COL_SHEET   = "_sheet"              # auto-added: which state/sheet the row came from

# ── Status filtering ────────────────────────────────────────────────────
# Rows whose Status matches any of these values will be SKIPPED
SKIP_STATUSES = {"decline", "declined"}

# ── Email validation ────────────────────────────────────────────────────
CHECK_MX_RECORD      = True    # DNS lookup to confirm domain receives mail
FLAG_PERSONAL_EMAIL  = True    # Warn on free/consumer domains
BLOCK_PERSONAL_EMAIL = False   # Set True to skip free/consumer domains

PERSONAL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.co.jp", "yahoo.com.br",
    "hotmail.com", "hotmail.com.br", "outlook.com", "live.com",
    "icloud.com", "me.com", "bol.com.br", "uol.com.br",
    "aol.com", "protonmail.com", "mail.com",
}

# ── Email content ────────────────────────────────────────────────────────
EMAIL_SUBJECT = "Cooperation for Passive Income"

# Path to body template file, or write the template inline here as a string.
# Placeholders: {name}
EMAIL_TEMPLATE = "templates/email_body.txt"

# ── Output & logging ────────────────────────────────────────────────────
OUTPUT_DIR   = "output"
LOG_FILE     = "logs/run.log"
SEND_HISTORY_FILE = "logs/send_history.json"

# DRY_RUN = True  → validate only, print what would be sent, NO emails sent
# DRY_RUN = False → actually send emails (you will be asked to confirm first)
DRY_RUN      = True

SEND_DELAY_S = 2    # seconds between sends (avoids Gmail rate limits)

# ── Send limits ─────────────────────────────────────────────────────────
# These are enforced across runs using SEND_HISTORY_FILE.
# Use conservative defaults, then raise only after your SMTP provider confirms limits.
MAX_SENDS_PER_HOUR = 40
MAX_SENDS_PER_DAY  = 300

# ── Gmail limits (informational) ────────────────────────────────────────
# Free Gmail:         ~500 emails/day
# Google Workspace:   ~2,000 emails/day

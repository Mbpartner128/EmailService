# Brazil Email Sender

Send emails to the 6-sheet Brazil client list via SMTP, with validation, filtering, hourly/daily send limits, and a color-coded Excel report.

## File Structure

```
email-sender/
├── main.py              ← Run this
├── config.py            ← All settings (edit before use)
├── validator.py         ← Format + MX + personal domain check
├── reader.py            ← Multi-sheet XLSX reader
├── sender.py            ← SMTP sender
├── rate_limiter.py      ← Hourly/daily send quota guard
├── report.py            ← 4-tab Excel result report
├── templates/
│   └── email_body.txt   ← Email body ({name} placeholder)
├── output/              ← Reports saved here
└── logs/
    ├── run.log          ← Full send log
    └── send_history.json ← Successful live sends used for hourly/daily limits
```

---

## Setup

### 1. Install dependencies
```bash
pip install openpyxl pandas dnspython
```

### 2. Configure SMTP

This project can reuse the sibling `../smtp/.env` file if it exists. A local `email-sender/.env` uses the same variables and takes priority:

```text
SMTP_SENDER_NAME=Your Company
SMTP_FROM=no-reply@example.com
SMTP_REPLY_TO=contact@example.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=no-reply@example.com
SMTP_PASSWORD=replace-with-your-password
SMTP_UNSUBSCRIBE_URL=https://example.com/unsubscribe
```

For Gmail, regular passwords don't work for SMTP. You need an App Password:

1. Enable **2-Step Verification**: https://myaccount.google.com/security
2. Create App Password: https://myaccount.google.com/apppasswords
3. Select **Mail** → **Other** → copy the 16-character code

### 3. Review `config.py`

```python
DRY_RUN = True
MAX_SENDS_PER_HOUR = 40
MAX_SENDS_PER_DAY = 300
```

### 4. Place Brazil.xlsx next to `main.py`

---

## Running

```bash
# Dry run (validate only, no emails sent) — default
python main.py

# Specify a different file path
python main.py /path/to/Brazil.xlsx

# Live send: set DRY_RUN = False in config.py, then:
python main.py
# → confirm with "y" when prompted
```

---

## Client List Format (Brazil.xlsx)

| Column | Used for |
|---|---|
| Name | `{name}` in email template + From display |
| Email Address | Send target + validation |
| Status | `decline` / `declined` → skipped automatically |

The 6 sheets (Maranhão, Alagoas, Piauí, Distrito Federal, Rio Grande do Sul, Santa Catarina) are all loaded automatically.

To target specific state(s), edit `config.py`:
```python
TARGET_SHEETS = ["Maranhão", "Alagoas"]  # or None for all
```

---

## Validation Logic

| Check | Result |
|---|---|
| Empty email | ❌ Skipped |
| Bad format (`bad@@email`) | ❌ Skipped |
| No MX record for domain | ❌ Skipped |
| Status = "decline" / "declined" | ⏭ Skipped |
| `@gmail.com`, `@hotmail.com`, etc. | ⚠️ Flagged but still sent by default (`BLOCK_PERSONAL_EMAIL = False`) |
| Corporate domain, MX resolves | ✅ Sent |

---

## Output Report (output/result_YYYYMMDD_HHMMSS.xlsx)

| Tab | Contents |
|---|---|
| **All Results** | Every row with color-coded status |
| **By State** | Counts per sheet (valid, invalid, sent, etc.) |
| **Ready to Send** | Only the sendable addresses |
| **Legend** | Color and column guide |

### Color Key

| Color | Meaning |
|---|---|
| 🟢 Green | Sent successfully |
| 🔵 Blue | Valid personal domain when `BLOCK_PERSONAL_EMAIL = False` |
| 🟡 Yellow | Not sent because hourly or daily send limit was reached |
| 🔴 Red | Invalid format or no MX — skipped |
| ⬜ Gray | Skipped (Status = decline, blocked personal domain if enabled, etc.) |

---

## Send Limits

The sender enforces both hourly and daily limits across multiple runs using `logs/send_history.json`.

| Setting | Default |
|---|---|
| `MAX_SENDS_PER_HOUR` | 40 |
| `MAX_SENDS_PER_DAY` | 300 |

`SEND_DELAY_S = 2` adds spacing between emails. The rate limiter stops sending when a quota is reached and marks the remaining rows in the Excel report.

For reference, Gmail is usually around 500/day for free accounts and around 2,000/day for Google Workspace. Your SMTP provider may be lower, so keep the configured limit conservative.

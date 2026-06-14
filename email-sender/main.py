#!/usr/bin/env python3
# main.py
import logging
import smtplib
import sys
from pathlib import Path
from collections import Counter

import config
from reader import load_clients
from validator import validate
from sender import Mailer
from report import write_report
from rate_limiter import SendRateLimiter

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def print_section(title: str):
    print(f"\n{'─'*58}")
    print(f"  {title}")
    print(f"{'─'*58}")


def run(xlsx_path: str = None):
    log.info("─── Brazil Email Sender started ───")

    # 1. Load
    print_section("Loading client list…")
    try:
        clients = load_clients(xlsx_path)
    except Exception as exc:
        log.error(f"Could not load client list: {exc}")
        return
    state_counts = Counter(c["_sheet"] for c in clients)
    print(f"  Loaded {len(clients):,} client(s) across {len(state_counts)} sheet(s):")
    for state, n in state_counts.items():
        print(f"    • {state}: {n:,}")

    # 2. Validate
    print_section(f"Validating {len(clients):,} email addresses…")

    results = []
    no_email    = 0
    invalid_fmt = 0
    no_mx       = 0
    personal    = 0
    skipped_st  = 0
    sendable_n  = 0
    duplicate_n = 0
    seen_emails = set()

    for c in clients:
        vr = validate(c["email"], c.get("status", ""))
        email_key = c["email"].strip().lower()
        duplicate = bool(email_key and email_key in seen_emails)
        if email_key:
            seen_emails.add(email_key)

        entry = {
            "_sheet":       c["_sheet"],
            "name":         c["name"],
            "email":        c["email"],
            "status":       c.get("status", ""),
            "valid":        vr.valid_format,
            "mx_ok":        vr.mx_ok,
            "mx_fail":      vr.mx_ok is False,
            "is_personal":  vr.is_personal,
            "skip_status":  vr.skip_status,
            "duplicate":    duplicate,
            "sendable":     vr.sendable and not duplicate,
            "notes":        vr.status_label,
            "sent":         False,
            "dry_run":      False,
            "send_failed":  False,
        }
        if duplicate:
            entry["notes"] += " | DUPLICATE: skipped"
        results.append(entry)

        if not c["email"]:                          no_email    += 1
        elif not vr.valid_format:                   invalid_fmt += 1
        if vr.mx_ok is False:                       no_mx       += 1
        if vr.is_personal:                          personal    += 1
        if vr.skip_status:                          skipped_st  += 1
        if duplicate:                               duplicate_n += 1
        if entry["sendable"]:                       sendable_n  += 1

    print(f"\n  Results:")
    print(f"    ✅  Sendable      : {sendable_n:,}")
    personal_note = "blocked" if config.BLOCK_PERSONAL_EMAIL else "still sendable"
    print(f"    ⚠️   Personal domain: {personal:,}  ({personal_note})")
    print(f"    ❌  No email addr : {no_email:,}")
    print(f"    ❌  Invalid format: {invalid_fmt:,}")
    print(f"    ❌  No MX record  : {no_mx:,}")
    print(f"    ⏭   Status skipped: {skipped_st:,}")
    print(f"    🔁  Duplicates    : {duplicate_n:,}")

    sendable = [r for r in results if r["sendable"]]

    if not sendable:
        log.warning("No sendable addresses found.")
        write_report(results)
        return

    limiter = SendRateLimiter()
    hourly_left, daily_left = limiter.remaining()
    allowed_now = min(len(sendable), hourly_left, daily_left)

    # 3. Confirm
    print_section("Ready to send")
    print(f"  📧  {len(sendable):,} email(s) queued")
    print(f"  📤  SMTP account : {config.SMTP_USER}")
    print(f"  🧪  DRY_RUN      : {config.DRY_RUN}")
    print(f"  🚦  Hourly limit : {hourly_left:,}/{config.MAX_SENDS_PER_HOUR:,} remaining")
    print(f"  🚦  Daily limit  : {daily_left:,}/{config.MAX_SENDS_PER_DAY:,} remaining")
    if config.DRY_RUN:
        print("\n  ℹ️  DRY_RUN = True → validation only, nothing will be sent.")
        print("  Set DRY_RUN = False in config.py to send for real.")
    else:
        if allowed_now <= 0:
            reason = limiter.limit_reason()
            log.warning(reason)
            for r in sendable:
                r["rate_limited"] = True
                r["notes"] += f" | NOT SENT: {reason}"
            write_report(results)
            return

        if allowed_now < len(sendable):
            print(f"  ⚠️   Limit cap     : only {allowed_now:,} will be sent this run")

        eta_min = (allowed_now * config.SEND_DELAY_S) // 60
        print(f"  ⏱   Est. time     : ~{eta_min} min  ({config.SEND_DELAY_S}s delay/email)")
        ans = input("\n  Proceed? [y/N] ").strip().lower()
        if ans != "y":
            log.info("Aborted by user.")
            write_report(results)
            return

    # 4. Send
    print_section("Sending…")
    mailer = Mailer()
    for idx, r in enumerate(sendable):
        if not config.DRY_RUN and not limiter.can_send():
            reason = limiter.limit_reason()
            r["rate_limited"] = True
            r["notes"] += f" | NOT SENT: {reason}"
            log.warning(f"Stopped before {r['email']}: {reason}")
            continue

        try:
            ok = mailer.send(r["email"], r["name"])
        except smtplib.SMTPAuthenticationError:
            reason = "SMTP AUTH FAILED"
            r["send_failed"] = True
            r["notes"] += f" | {reason}"
            log.error("Stopping send run because SMTP authentication failed.")
            remaining = sendable[idx + 1:]
            for pending in remaining:
                pending["send_failed"] = True
                pending["notes"] += f" | NOT SENT: {reason}"
            mailer.failed += 1 + len(remaining)
            break

        r["sent"]        = ok and not config.DRY_RUN
        r["dry_run"]     = ok and config.DRY_RUN
        r["send_failed"] = not ok and not config.DRY_RUN
        if ok and not config.DRY_RUN:
            limiter.record_send()
        if not ok:
            r["notes"] += " | SEND FAILED"

    if config.DRY_RUN:
        dry_run_n = sum(1 for r in results if r.get("dry_run"))
        print(f"\n  🧪 Would send: {dry_run_n:,}")
    else:
        print(f"\n  ✅ Sent    : {mailer.sent:,}")
    print(f"  ❌ Failed  : {mailer.failed:,}")

    # 5. Report
    write_report(results)


if __name__ == "__main__":
    xlsx = sys.argv[1] if len(sys.argv) > 1 else None
    run(xlsx)

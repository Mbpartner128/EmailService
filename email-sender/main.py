#!/usr/bin/env python3
# main.py
import argparse
import logging
import smtplib
import sys
from pathlib import Path
from collections import Counter

import config
from reader import load_clients, first_name
from validator import validate
from sender import Mailer, send_email, preview_email
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
    print(f"\n{'-'*58}")
    print(f"  {title}")
    print(f"{'-'*58}")


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
            "first_name":   c.get("first_name", c["name"]),
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
            ok = mailer.send(r["email"], r["first_name"], r["name"])
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


def run_test(full_name: str, email: str, send: bool = False, yes: bool = False) -> int:
    log.info("--- Test email ---")
    print_section("Test email")
    print(f"  Name       : {full_name}")
    print(f"  First name : {first_name(full_name)}")
    print(f"  Email      : {email}")
    print(f"  SMTP from  : {config.SMTP_FROM}")
    print(f"  Subject    : {config.EMAIL_SUBJECT}")

    vr = validate(email)
    validation_parts = []
    if vr.valid_format:
        validation_parts.append("format OK")
    if vr.mx_ok is True:
        validation_parts.append("MX OK")
    elif vr.mx_ok is False:
        validation_parts.append("MX failed")
    if vr.is_personal:
        validation_parts.append("personal domain")
    print(f"  Validation : {', '.join(validation_parts) or 'invalid'}")
    if not vr.valid_format:
        log.error("Invalid email address.")
        return 1

    greeting = first_name(full_name)
    body = preview_email(greeting)
    print("\n  Preview:")
    print("  " + "-" * 54)
    for line in body.splitlines():
        print(f"  {line}")
    print("  " + "-" * 54)

    if not send:
        print("\n  Dry run only. Add --send to deliver this test email.")
        return 0

    ans = "y" if yes else input("\n  Send this test email? [y/N] ").strip().lower()
    if ans != "y":
        log.info("Test send aborted.")
        return 0

    print_section("Sending test email…")
    try:
        ok = send_email(email, greeting, full_name)
    except smtplib.SMTPAuthenticationError:
        log.error("SMTP authentication failed.")
        return 1

    if ok:
        print(f"\n  ✅ Test email sent to {email}")
        return 0

    print(f"\n  ❌ Failed to send test email to {email}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send emails from a Brazil client XLSX list, or send one test email."
    )
    subparsers = parser.add_subparsers(dest="command")

    test = subparsers.add_parser("test", help="Send one test email to a specific name and address.")
    test.add_argument("--name", required=True, help='Full name, e.g. "Casimiro Rocha"')
    test.add_argument("--email", required=True, help='Recipient email, e.g. "you@example.com"')
    test.add_argument("--send", action="store_true", help="Actually send. Without this, preview only.")
    test.add_argument("--yes", action="store_true", help="Skip confirmation prompt when using --send.")

    send = subparsers.add_parser("send", help="Validate and send emails from an XLSX client list.")
    send.add_argument("xlsx", nargs="?", help="Path to the client XLSX file.")

    return parser


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] not in {"test", "send"} and not sys.argv[1].startswith("-"):
        run(sys.argv[1])
        raise SystemExit(0)

    args = build_parser().parse_args()
    if args.command == "test":
        raise SystemExit(run_test(args.name, args.email, send=args.send, yes=args.yes))
    if args.command == "send":
        run(args.xlsx)
        raise SystemExit(0)

    run(None)

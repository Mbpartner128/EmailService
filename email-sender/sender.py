# sender.py
import smtplib
import ssl
import time
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from pathlib import Path
import config

log = logging.getLogger(__name__)


def _load_template() -> str:
    p = Path(config.EMAIL_TEMPLATE)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return config.EMAIL_TEMPLATE   # treat as inline string


def _render(template: str, name: str) -> str:
    return template.replace("{name}", name)


def preview_email(greeting_name: str) -> str:
    return _render(_load_template(), greeting_name)


def send_email(to_addr: str, greeting_name: str, display_name: str = "") -> bool:
    template = _load_template()
    body = _render(template, greeting_name)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = config.EMAIL_SUBJECT
    msg["From"]    = formataddr((config.SENDER_NAME, config.SMTP_FROM))
    to_label = display_name or greeting_name
    msg["To"]      = formataddr((to_label, to_addr)) if to_label else to_addr
    if config.SMTP_REPLY_TO:
        msg["Reply-To"] = config.SMTP_REPLY_TO
    if config.SMTP_UNSUBSCRIBE_URL:
        msg["List-Unsubscribe"] = f"<{config.SMTP_UNSUBSCRIBE_URL}>"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        context = ssl.create_default_context()
        security = "starttls" if config.SMTP_SECURITY == "tls" else config.SMTP_SECURITY

        if security == "ssl":
            srv_factory = smtplib.SMTP_SSL
            srv_kwargs = {"context": context}
        else:
            srv_factory = smtplib.SMTP
            srv_kwargs = {}

        with srv_factory(config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_TIMEOUT_S, **srv_kwargs) as srv:
            if security != "ssl":
                srv.ehlo()
            if security == "starttls":
                srv.starttls(context=context)
                srv.ehlo()
            srv.login(config.SMTP_USER, config.SMTP_PASS)
            srv.sendmail(config.SMTP_FROM, to_addr, msg.as_bytes())
        log.info(f"SENT → {to_addr}")
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("SMTP auth failed — verify SMTP_USERNAME / SMTP_PASSWORD in .env")
        raise
    except Exception as e:
        log.error(f"Failed → {to_addr}: {e}")
        return False


class Mailer:
    def __init__(self):
        self.sent    = 0
        self.failed  = 0

    def send(self, to_addr: str, greeting_name: str, display_name: str = "") -> bool:
        if config.DRY_RUN:
            log.info(f"[DRY RUN] → {to_addr} ({greeting_name})")
            return True
        ok = send_email(to_addr, greeting_name, display_name)
        if ok:
            self.sent += 1
            time.sleep(config.SEND_DELAY_S)
        else:
            self.failed += 1
        return ok

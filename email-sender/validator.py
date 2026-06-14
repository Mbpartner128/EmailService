# validator.py
import re
import socket
from dataclasses import dataclass
from typing import Optional
import config

EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
)

_mx_cache: dict[str, bool] = {}


@dataclass
class ValidationResult:
    email: str
    valid_format: bool
    mx_ok: Optional[bool]       # None = not checked
    is_personal: bool
    skip_status: bool           # True if status says decline etc.
    error: Optional[str]

    @property
    def sendable(self) -> bool:
        if self.skip_status:
            return False
        if not self.valid_format:
            return False
        if self.mx_ok is False:
            return False
        if self.is_personal and config.BLOCK_PERSONAL_EMAIL:
            return False
        return True

    @property
    def status_label(self) -> str:
        if self.skip_status:
            return "⏭  Skipped (status)"
        if not self.valid_format:
            return "❌ Invalid format"
        parts = []
        if self.is_personal:
            label = "⚠️  Personal domain"
            if config.BLOCK_PERSONAL_EMAIL:
                label += " (blocked)"
            parts.append(label)
        if self.mx_ok is False:
            parts.append("❌ No MX record")
        elif self.mx_ok is True:
            parts.append("✅ MX OK")
        return " | ".join(parts) if parts else "✅ OK"


def _check_mx(domain: str) -> bool:
    if domain in _mx_cache:
        return _mx_cache[domain]
    try:
        import dns.resolver
        dns.resolver.resolve(domain, 'MX', lifetime=5)
        result = True
    except Exception:
        try:
            socket.getaddrinfo(domain, None)
            result = True
        except socket.gaierror:
            result = False
    _mx_cache[domain] = result
    return result


def validate(email: str, status: str = "") -> ValidationResult:
    email = email.strip() if email else ""

    # Status filter
    skip_status = status.strip().lower() in config.SKIP_STATUSES

    # Format
    fmt_ok = bool(EMAIL_REGEX.match(email))
    if not fmt_ok:
        return ValidationResult(
            email=email, valid_format=False,
            mx_ok=None, is_personal=False,
            skip_status=skip_status,
            error="Invalid email format" if email else "No email address",
        )

    domain = email.split("@")[1].lower()
    personal = domain in config.PERSONAL_DOMAINS if config.FLAG_PERSONAL_EMAIL else False
    mx_ok = None

    if config.CHECK_MX_RECORD and not skip_status:
        mx_ok = _check_mx(domain)

    err = None
    if mx_ok is False:
        err = f"No MX record: {domain}"

    return ValidationResult(
        email=email, valid_format=True,
        mx_ok=mx_ok, is_personal=personal,
        skip_status=skip_status,
        error=err,
    )

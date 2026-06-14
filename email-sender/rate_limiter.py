import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config


class SendRateLimiter:
    """Persists successful send timestamps so limits survive multiple runs."""

    def __init__(self, path: str = None):
        self.path = Path(path or config.SEND_HISTORY_FILE)
        self.timestamps = self._load()
        self._prune()

    def _load(self) -> list[datetime]:
        if not self.path.exists():
            return []

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

        timestamps = []
        for value in raw:
            try:
                timestamps.append(datetime.fromisoformat(value))
            except (TypeError, ValueError):
                continue
        return timestamps

    def _prune(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        self.timestamps = [ts for ts in self.timestamps if ts >= cutoff]

    def _save(self) -> None:
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(
            json.dumps([ts.isoformat() for ts in self.timestamps], indent=2),
            encoding="utf-8",
        )

    def counts(self) -> tuple[int, int]:
        now = datetime.now(timezone.utc)
        hour_cutoff = now - timedelta(hours=1)
        day_cutoff = now - timedelta(days=1)
        sent_last_hour = sum(1 for ts in self.timestamps if ts >= hour_cutoff)
        sent_last_day = sum(1 for ts in self.timestamps if ts >= day_cutoff)
        return sent_last_hour, sent_last_day

    def remaining(self) -> tuple[int, int]:
        sent_last_hour, sent_last_day = self.counts()
        hourly_left = max(0, config.MAX_SENDS_PER_HOUR - sent_last_hour)
        daily_left = max(0, config.MAX_SENDS_PER_DAY - sent_last_day)
        return hourly_left, daily_left

    def can_send(self) -> bool:
        hourly_left, daily_left = self.remaining()
        return hourly_left > 0 and daily_left > 0

    def limit_reason(self) -> str:
        hourly_left, daily_left = self.remaining()
        if daily_left <= 0:
            return f"Daily send limit reached ({config.MAX_SENDS_PER_DAY}/day)"
        if hourly_left <= 0:
            return f"Hourly send limit reached ({config.MAX_SENDS_PER_HOUR}/hour)"
        return ""

    def record_send(self) -> None:
        self.timestamps.append(datetime.now(timezone.utc))
        self._prune()
        self._save()

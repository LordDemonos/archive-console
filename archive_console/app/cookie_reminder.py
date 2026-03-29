"""Cookie hygiene N-day reminder: visibility rules and copy (in-app only, no secrets)."""

from __future__ import annotations

import time

from .settings import CookieHygieneSettings

# Primary text: Firefox + YouTube; path matches nav "Inputs & config → cookies.txt"
COOKIE_REMINDER_MESSAGE = (
    "You may need fresh YouTube authentication cookies. In Firefox, stay logged into YouTube, "
    "export cookies for youtube.com (Netscape format), then save them as cookies.txt under "
    "Inputs & config (replace the existing file). Re-run your archive after updating."
)

SECONDARY_LINE = (
    "Next: open Firefox → visit youtube.com while signed in → export per your tool’s docs → "
    "place cookies.txt → use Unlock cookies in the editor if needed → run again."
)


def _message_body() -> str:
    return f"{COOKIE_REMINDER_MESSAGE} {SECONDARY_LINE}"


def cookie_reminder_is_due(ch: CookieHygieneSettings, *, now: float | None = None) -> bool:
    """True when the N-day cadence says the operator should see the banner (server clock)."""
    t = time.time() if now is None else now
    if ch.remind_interval_days <= 0:
        return False
    if ch.snooze_until_unix and t < ch.snooze_until_unix:
        return False
    # last_acknowledged_unix == 0 means never started — do not treat as "due immediately"
    if ch.last_acknowledged_unix <= 0:
        return False
    interval_sec = ch.remind_interval_days * 86400
    return (t - ch.last_acknowledged_unix) >= interval_sec


def cookie_reminder_payload(
    ch: CookieHygieneSettings, *, now: float | None = None
) -> dict[str, str | bool]:
    if not cookie_reminder_is_due(ch, now=now):
        return {"show": False, "message": ""}
    return {"show": True, "message": _message_body()}


def cookie_hygiene_anchor_if_needed(ch: CookieHygieneSettings) -> CookieHygieneSettings:
    """When enabling N-day reminders with no prior ack time, start the clock at \"now\" (no instant nag)."""
    if ch.remind_interval_days > 0 and ch.last_acknowledged_unix <= 0:
        return ch.model_copy(update={"last_acknowledged_unix": time.time()})
    return ch

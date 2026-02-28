#!/usr/bin/env python3

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from icalendar import Calendar


SCRIPT_DIR = Path(__file__).parent.resolve()
SENT_EVENTS_FILE = SCRIPT_DIR / "sent_events.json"
ENV_FILE = SCRIPT_DIR / ".env"
LOG_FILE = SCRIPT_DIR / "luma_notifier.log"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def load_env():
    """Load environment variables from .env file if it exists."""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                os.environ.setdefault(key, value)


load_env()


GOOGLE_CALENDAR_ICS_URL = os.environ.get("GOOGLE_CALENDAR_ICS_URL", "")
FRIEND_PHONE_NUMBER = os.environ.get("FRIEND_PHONE_NUMBER", "")


def check_config():
    """Verify all required env vars are set."""
    missing = []
    for var in ["GOOGLE_CALENDAR_ICS_URL", "FRIEND_PHONE_NUMBER"]:
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        log.error(f"Missing environment variables: {', '.join(missing)}")
        log.error(f"Set them in {ENV_FILE}")
        sys.exit(1)



def fetch_calendar() -> Calendar:
    """Download and parse the ICS calendar feed."""
    log.info("Fetching Google Calendar ICS feed...")
    resp = requests.get(GOOGLE_CALENDAR_ICS_URL, timeout=30)
    resp.raise_for_status()
    log.info(f"Downloaded {len(resp.content)} bytes")
    return Calendar.from_ical(resp.content)


def extract_luma_events(cal: Calendar, days_ahead: int = 30) -> list[dict]:
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days_ahead)
    luma_events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        uid = str(component.get("UID", ""))
        organizer = str(component.get("ORGANIZER", ""))
        description = str(component.get("DESCRIPTION", ""))

        is_luma = (
            "lu.ma" in organizer.lower()
            or "events.lu.ma" in uid.lower()
            or "lu.ma" in description.lower()
            or "luma.com" in description.lower()
        )

        if not is_luma:
            continue

        attendees = component.get("ATTENDEE")
        if attendees is None:
            continue

        if not isinstance(attendees, list):
            attendees = [attendees]

        user_accepted = False
        for attendee in attendees:
            partstat = attendee.params.get("PARTSTAT", "")
            email = str(attendee).lower()
            if partstat == "ACCEPTED" and "sreeprasad" in email:
                user_accepted = True
                break

        if not user_accepted:
            continue

        dtstart = component.get("DTSTART")
        if dtstart is None:
            continue

        start_dt = dtstart.dt
        if not hasattr(start_dt, "hour"):
            start_dt = datetime.combine(start_dt, datetime.min.time()).replace(
                tzinfo=timezone.utc
            )
        elif start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        if start_dt < now or start_dt > cutoff:
            continue

        summary = str(component.get("SUMMARY", "Untitled Event"))
        location = str(component.get("LOCATION", ""))

        luma_url = ""
        url_match = re.search(
            r"https?://(?:lu\.ma|luma\.com)/(?:event/|e/|join/)?[^\s\\]+",
            description,
        )
        if url_match:
            luma_url = url_match.group(0).rstrip("\\n").rstrip("\\")

        event_id = uid.split("@")[0] if "@" in uid else uid

        luma_events.append(
            {
                "id": event_id,
                "name": summary,
                "start_at": start_dt.isoformat(),
                "location": location,
                "url": luma_url,
            }
        )

    luma_events.sort(key=lambda e: e["start_at"])
    return luma_events


def load_sent_events() -> set[str]:
    if not SENT_EVENTS_FILE.exists():
        return set()
    try:
        data = json.loads(SENT_EVENTS_FILE.read_text())
        return set(data.get("sent_event_ids", []))
    except (json.JSONDecodeError, KeyError):
        return set()


def save_sent_events(sent_ids: set[str]) -> None:
    data = {
        "sent_event_ids": sorted(sent_ids),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    SENT_EVENTS_FILE.write_text(json.dumps(data, indent=2))
    log.info(f"Saved {len(sent_ids)} sent event IDs")


def send_imessage(message: str) -> bool:
    """Send an iMessage/SMS via macOS Messages.app using AppleScript."""
    escaped_message = message.replace("\\", "\\\\").replace('"', '\\"')
    escaped_phone = FRIEND_PHONE_NUMBER.replace('"', '\\"')

    applescript = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "{escaped_phone}" of targetService
        send "{escaped_message}" to targetBuddy
    end tell
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            log.info("iMessage sent successfully!")
            return True
        else:
            log.error(f"AppleScript error: {result.stderr.strip()}")
            return _send_sms_fallback(escaped_message, escaped_phone)
    except subprocess.TimeoutExpired:
        log.error("AppleScript timed out")
        return False
    except Exception as e:
        log.error(f"Failed to send iMessage: {e}")
        return False


def _send_sms_fallback(message: str, phone: str) -> bool:
    """Fallback to SMS if iMessage fails (e.g., friend is on Android)."""
    log.info("Trying SMS fallback...")
    applescript = f'''
    tell application "Messages"
        send "{message}" to buddy "{phone}" of service "SMS"
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            log.info("SMS sent successfully!")
            return True
        else:
            log.error(f"SMS fallback also failed: {result.stderr.strip()}")
            return False
    except Exception as e:
        log.error(f"SMS fallback error: {e}")
        return False


def format_message(events: list[dict]) -> str:
    """Format all new events into a single message."""
    lines = []

    if len(events) == 1:
        e = events[0]
        lines.append("Hey! I just registered for an event:")
        lines.append("")
        lines.append(e["name"])
        date_str = _format_date(e.get("start_at", ""))
        if date_str:
            lines.append(date_str)
        if e["url"]:
            lines.append(e["url"])
    else:
        lines.append(f"Hey! I just registered for {len(events)} events:")
        lines.append("")
        for i, e in enumerate(events, 1):
            lines.append(f"{i}. {e['name']}")
            date_str = _format_date(e.get("start_at", ""))
            if date_str:
                lines.append(f"   {date_str}")
            if e["url"]:
                lines.append(f"   {e['url']}")
            lines.append("")

    return "\n".join(lines)


def _format_date(start: str) -> str:
    if not start:
        return ""
    try:
        dt = datetime.fromisoformat(start)
        return dt.strftime("%a, %b %d at %I:%M %p")
    except (ValueError, TypeError):
        return start


def main():
    log.info("=" * 50)
    log.info("Luma → iMessage Notifier starting...")
    log.info("=" * 50)

    check_config()

    try:
        cal = fetch_calendar()
    except Exception as e:
        log.error(f"Failed to fetch calendar: {e}")
        sys.exit(1)

    events = extract_luma_events(cal, days_ahead=30)
    log.info(f"Found {len(events)} upcoming Luma events you've RSVPed to:")
    for e in events:
        log.info(f"  - {e['name']} ({e['id']}) on {e['start_at']}")

    if not events:
        log.info("No upcoming Luma events. Done.")
        return

    sent_ids = load_sent_events()
    new_events = [e for e in events if e["id"] not in sent_ids]
    log.info(f"New events to send: {len(new_events)}")

    if not new_events:
        log.info("No new events. Nothing to send.")
        return

    message = format_message(new_events)
    log.info(f"Sending iMessage with {len(new_events)} event(s)...")

    if send_imessage(message):
        sent_ids.update(e["id"] for e in new_events)
        save_sent_events(sent_ids)
        log.info(f"Done! Sent {len(new_events)} new event(s).")
    else:
        log.error("iMessage send failed. Events NOT marked as sent (will retry next run).")


if __name__ == "__main__":
    main()

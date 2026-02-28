# Luma iMessage Notifier

A zero-cost macOS automation that monitors your Luma event registrations and
texts them to a friend via iMessage.

```
Google Calendar ICS to Python (filter Luma events) to iMessage via AppleScript
```

## How It Works

When you RSVP to a Luma event, Luma sends a Google Calendar invite with structured metadata:

```
ORGANIZER: calendar-invite@lu.ma
UID: evt-XXXXX@events.lu.ma
PARTSTAT: ACCEPTED
```

This script uses that by:

1. **Fetching** your Google Calendar's private ICS feed (no OAuth, just a URL)
2. **Filtering** for events where the organizer is `@lu.ma` and your RSVP status is `ACCEPTED`
3. **Diffing** against `sent_events.json` to find new registrations
4. **Sending** new events to your friend via iMessage (AppleScript → Messages.app)
5. **Scheduling** via macOS `launchctl` — runs daily, catches up after sleep

## Why This Approach?

I originally built this with Twilio WhatsApp + GitHub Actions. Then I realized:

- Google Calendar already has all the data (no need to hit the Luma API)
- macOS can send iMessages for free (no need for Twilio at $0.005/msg)
- `launchctl` runs missed jobs on wake (no need for a cloud server)

**Total cost: $0. Total dependencies: 2.**

## Setup

### Prerequisites

- macOS with Messages.app signed in
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (or pip)

### 1. Get your Google Calendar ICS URL

- Go to [Google Calendar Settings](https://calendar.google.com/calendar/r/settings)
- Click on the calendar where your Luma events appear
- Copy the **"Secret address in iCal format"** URL

> ⚠️ This URL is a secret — anyone with it can read your calendar. Never commit it.

### 2. Clone and configure

```bash
git clone https://github.com/sreeprasad/luma_notifier.git
cd luma_notifier

cp .env.example .env
```

Edit `.env` with your values:

```env
GOOGLE_CALENDAR_ICS_URL=https://calendar.google.com/calendar/ical/...private-.../basic.ics
FRIEND_PHONE_NUMBER=+19876543219
```

### 3. Install

```bash
chmod +x install.sh
./install.sh
```

The installer will:
- Create a `.venv` with `uv`
- Install dependencies (`requests`, `icalendar`)
- Run a test to verify calendar parsing works
- Generate and load a `launchctl` job to run daily at 6 PM

### 4. Grant Automation permissions

On first run, macOS will ask to let Terminal control Messages.app. Say yes.

You can also set this manually: 
**System Settings to Privacy & Security to Automation to Terminal to Messages.app**

## Usage

```bash
# Run
chmod +x install.sh
./install.sh

# Run manually
.venv/bin/python luma_imessage.py

# Check logs
cat luma_notifier.log

# See what's been sent
cat sent_events.json

# Trigger the launchctl job now
launchctl start com.luma-imessage-notifier

# Uninstall
launchctl unload ~/Library/LaunchAgents/com.luma-imessage-notifier.plist
rm ~/Library/LaunchAgents/com.luma-imessage-notifier.plist
```

## How the iMessage Sending Works

Under the hood, it's a 4-line AppleScript executed via `osascript`:

```applescript
tell application "Messages"
    set targetService to 1st account whose service type = iMessage
    set targetBuddy to participant "+19876543219" of targetService
    send "Hey! I just registered for..." to targetBuddy
end tell
```

If iMessage fails (e.g., friend is on Android), it falls back to SMS relay via your iPhone.

## Customization

| What | Where |
|---|---|
| Change schedule time | Edit `Hour` and `Minute` in `install.sh`, then re-run it |
| Change lookahead window | Edit `days_ahead=30` in `luma_imessage.py` |
| Change message format | Edit `format_message()` in `luma_imessage.py` |
| Send to multiple friends | Duplicate the `send_imessage()` call with different numbers |
| Filter different calendar events | Modify `is_luma` check in `extract_luma_events()` |

## License

MIT

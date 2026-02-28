#!/bin/bash
# ─── Luma iMessage Notifier — Installer ──────────────────
# Run this once: ./install.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_LABEL="com.luma-imessage-notifier"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "══════════════════════════════════════════════"
echo "  Luma → iMessage Notifier Installer"
echo "══════════════════════════════════════════════"
echo ""
echo "Script directory: $SCRIPT_DIR"
echo ""

# ── Step 1: Check .env ──
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "❌ .env file not found!"
    echo "   Copy .env.example to .env and fill in your values:"
    echo ""
    echo "   cp .env.example .env"
    echo "   nano .env"
    echo ""
    exit 1
fi
echo "✅ .env file found"

# ── Step 2: Check uv is installed ──
if ! command -v uv &> /dev/null; then
    echo ""
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "✅ uv found: $(which uv)"

# ── Step 3: Create venv and install dependencies ──
echo ""
echo "Setting up virtual environment with uv..."
uv venv "$VENV_DIR"
uv pip install -r "$SCRIPT_DIR/requirements.txt" -p "$VENV_DIR/bin/python"
PYTHON_PATH="$VENV_DIR/bin/python"
echo "✅ Dependencies installed (requests, icalendar)"
echo "   Python: $PYTHON_PATH"

# ── Step 4: Test the script ──
echo ""
echo "Testing the script..."
cd "$SCRIPT_DIR"
"$PYTHON_PATH" luma_imessage.py
echo ""
echo "✅ Script ran successfully (check above for any events found)"

# ── Step 5: Grant permissions reminder ──
echo ""
echo "⚠️  IMPORTANT: Grant Terminal permissions for iMessage"
echo "   System Settings → Privacy & Security → Automation"
echo "   Make sure Terminal (or iTerm) can control Messages.app"
echo ""
read -p "Have you granted Automation permissions? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Please grant permissions first, then re-run ./install.sh"
    exit 1
fi

# ── Step 6: Generate and install launchctl plist ──
echo ""
echo "Setting up daily launchctl job..."

# Unload existing job if present
launchctl unload "$PLIST_DEST" 2>/dev/null || true

cat > "$PLIST_DEST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$SCRIPT_DIR/luma_imessage.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>18</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/launchctl_stdout.log</string>

    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/launchctl_stderr.log</string>
</dict>
</plist>
PLIST

echo "   Plist generated at: $PLIST_DEST"

# ── Step 7: Load the launch agent ──
launchctl load "$PLIST_DEST"

echo "✅ Launch agent loaded"
echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ All done!"
echo "══════════════════════════════════════════════"
echo ""
echo "The notifier will run daily at 6:00 PM."
echo "If your laptop is asleep, it runs when you open it."
echo ""
echo "Useful commands:"
echo "  Test now:    cd $SCRIPT_DIR && $PYTHON_PATH luma_imessage.py"
echo "  View logs:   cat $SCRIPT_DIR/luma_notifier.log"
echo "  Uninstall:   launchctl unload $PLIST_DEST && rm $PLIST_DEST"
echo "  Check state: cat $SCRIPT_DIR/sent_events.json"
echo ""

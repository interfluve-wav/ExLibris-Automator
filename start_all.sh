#!/bin/bash

# Always use the directory containing this script as repo root (not the caller's cwd).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Esploro Citation Automation - Unified Launcher
# Runs Discord bot, terminal monitor, and Flask web GUI together

echo "🚀 Starting ExLibris Automator..."
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create log directory
mkdir -p logs

# Ensure single-instance local stack (avoid duplicate bots/workers).
if pgrep -f "discord_bot_batch_smart.py" >/dev/null; then
    echo -e "${YELLOW}⚠ Found existing Discord bot process(es). Stopping old instances...${NC}"
    pkill -f "discord_bot_batch_smart.py" 2>/dev/null || true
    sleep 1
fi
if pgrep -f "esp_gui_web.py" >/dev/null; then
    echo -e "${YELLOW}⚠ Found existing Flask GUI process(es). Stopping old instances...${NC}"
    pkill -f "esp_gui_web.py" 2>/dev/null || true
    sleep 1
fi
pkill -f "automation.worker" 2>/dev/null || true

# Cleanup function to kill all processes on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Shutting down all services...${NC}"

    if [ ! -z "$DISCORD_PID" ]; then
        kill $DISCORD_PID 2>/dev/null
        echo -e "${GREEN}✓ Discord bot stopped${NC}"
    fi

    if [ ! -z "$FLASK_PID" ]; then
        kill $FLASK_PID 2>/dev/null
        echo -e "${GREEN}✓ Flask web GUI stopped${NC}"
    fi

    # Kill any remaining worker processes
    pkill -f "automation.worker" 2>/dev/null

    echo -e "${GREEN}✓ All services stopped${NC}"
    exit 0
}

# Set trap to cleanup on exit
trap cleanup SIGINT SIGTERM EXIT

# Start Discord bot via core launcher (single source of truth)
echo -e "${BLUE}🤖 Starting Discord bot (via start_smart_batch.sh)...${NC}"
./start_smart_batch.sh > logs/discord_bot.log 2>&1 &
DISCORD_PID=$!
sleep 3

# Check if Discord bot started successfully
if ! ps -p $DISCORD_PID > /dev/null; then
    echo -e "${RED}❌ Discord bot failed to start. Check logs/discord_bot.log${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Discord bot launcher running (PID: $DISCORD_PID)${NC}"

# Start Flask web GUI
echo -e "${BLUE}🌐 Starting Flask web GUI...${NC}"
if [ -x ".venv/bin/python3" ]; then
    FLASK_PYTHON=".venv/bin/python3"
else
    FLASK_PYTHON="python3"
fi
"$FLASK_PYTHON" esp_gui_web.py > logs/flask_gui.log 2>&1 &
FLASK_PID=$!
sleep 2

# Check if Flask started successfully
if ! ps -p $FLASK_PID > /dev/null; then
    echo -e "${RED}❌ Flask web GUI failed to start. Check logs/flask_gui.log${NC}"
    kill $DISCORD_PID 2>/dev/null
    exit 1
fi

echo -e "${GREEN}✓ Flask web GUI running (PID: $FLASK_PID)${NC}"
echo ""

# Display status and URLs
echo "=================================================="
echo -e "${GREEN}✅ All services running successfully!${NC}"
echo "=================================================="
echo ""
echo -e "${BLUE}📊 Service Status:${NC}"
echo "   • Discord Bot:  Running (PID: $DISCORD_PID)"
echo "   • Flask Web UI: Running (PID: $FLASK_PID)"
echo ""
echo -e "${BLUE}🌐 Access Points:${NC}"
echo "   • Web Interface: http://localhost:8765"
echo "   • Discord Channel: Use configured channel"
echo ""
echo -e "${BLUE}📝 Logs:${NC}"
echo "   • Discord: tail -f logs/discord_bot.log"
echo "   • Flask:   tail -f logs/flask_gui.log"
echo ""
echo -e "${BLUE}💡 Discord Commands:${NC}"
echo "   !f or !fill      - Fill next citation"
echo "   !queue           - Show queued citations"
echo "   !skip            - Skip current citation"
echo "   !close           - Close browser"
echo "   !clear           - Clear queue"
echo "   /set_type        - Set asset type"
echo "   /set_researcher  - Set researcher"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo "=================================================="
echo ""

# Monitor processes and keep script alive
while true; do
    # Check if Discord bot is still running
    if ! ps -p $DISCORD_PID > /dev/null; then
        echo -e "${RED}❌ Discord bot crashed! Check logs/discord_bot.log${NC}"
        cleanup
    fi

    # Check if Flask is still running
    if ! ps -p $FLASK_PID > /dev/null; then
        echo -e "${RED}❌ Flask web GUI crashed! Check logs/flask_gui.log${NC}"
        cleanup
    fi

    sleep 5
done

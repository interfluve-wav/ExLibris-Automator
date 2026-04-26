#!/bin/bash
# Start a virtual display and expose it via VNC
# so headed Playwright browser windows are visible

export DISPLAY=:99

# Kill any existing Xvfb/x11vnc and clean up lock files
pkill -f "Xvfb :99" 2>/dev/null || true
pkill -f x11vnc 2>/dev/null || true
sleep 0.5
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true

# Start virtual display
Xvfb :99 -screen 0 1280x900x24 &
XVFB_PID=$!
echo "Xvfb started (PID $XVFB_PID) on display :99"

# Wait for Xvfb to be ready
sleep 2

# Allow all local X clients to connect (no auth required)
DISPLAY=:99 xhost + 2>/dev/null || true

# Start VNC server (no password, shared, loop forever)
x11vnc -display :99 -nopw -forever -shared -quiet &
X11VNC_PID=$!
echo "x11vnc started (PID $X11VNC_PID)"

echo "Virtual desktop is running on DISPLAY=:99"
echo "To run the automation worker with a visible browser:"
echo "  DISPLAY=:99 python automation/worker.py ..."

# Keep the script alive
wait $XVFB_PID

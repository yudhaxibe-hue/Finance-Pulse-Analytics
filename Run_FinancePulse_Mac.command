#!/bin/bash
# ==============================================================================
# Finance Pulse Analytics - 1-Click macOS Launcher
# Double-click in Finder to start locally in a native desktop window.
# ==============================================================================
set -e
cd "$(dirname "$0")"

clear
echo "=================================================================="
echo "  Finance Pulse Analytics"
echo "  Enterprise Financial Performance Intelligence &"
echo "  Profitability Optimization Analytics Platform"
echo "=================================================================="
echo ""

if [ -x ".venv/bin/python" ]; then
    VENV_DIR=".venv"
elif [ -x "venv/bin/python" ]; then
    VENV_DIR="venv"
else
    if command -v python3 >/dev/null 2>&1; then
        PY_CMD="python3"
    elif command -v python >/dev/null 2>&1; then
        PY_CMD="python"
    else
        echo "[ERROR] Python 3 is not installed on this Mac."
        echo "Download the standalone pre-packaged Mac application from GitHub Releases."
        read -r -p "Press Enter to exit..."
        exit 1
    fi
    VENV_DIR=".venv"
    echo "[Setup] Creating local virtual environment (first run only)..."
    "$PY_CMD" -m venv "$VENV_DIR"
    "$VENV_DIR/bin/python" -m pip install --upgrade pip
    "$VENV_DIR/bin/pip" install -r requirements-desktop.txt
    echo "[OK] Local environment ready."
    echo ""
fi

echo "Starting desktop window..."
exec "$VENV_DIR/bin/python" -m app_launcher "$@"

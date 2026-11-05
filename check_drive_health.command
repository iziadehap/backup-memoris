#!/bin/bash
# Double-clickable macOS Finder script to check external hard drive health
cd "$(dirname "$0")"
python3 check_drive_health.py
echo ""
read -p "Press [Enter] to close this window..."

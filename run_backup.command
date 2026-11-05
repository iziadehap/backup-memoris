#!/bin/bash
# ==============================================================================
# Double-clickable macOS launcher for backup.py
# ==============================================================================

# Move to the script's directory
cd "$(dirname "$0")"

echo "=================================================================="
echo "    Samsung Android -> External Hard Drive Backup"
echo "=================================================================="
echo "Current directory: $(pwd)"
echo ""

# Run backup script with Python 3
python3 backup.py

echo ""
echo "=================================================================="
echo "  Backup process has completed."
echo "=================================================================="
read -p "Press [Enter] to close this window..."

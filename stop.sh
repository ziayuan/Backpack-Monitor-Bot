#!/bin/bash

# Find and kill the monitor bot process
# We use pkill to match the command line
if pkill -f "python -u monitor.py"; then
    echo "🛑 Monitor bot stopped."
elif pkill -f "python monitor.py"; then
    echo "🛑 Monitor bot stopped."
else
    echo "⚠️ No running monitor bot found."
fi

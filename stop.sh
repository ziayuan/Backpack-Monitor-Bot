#!/bin/bash

# Find and kill the monitor bot process
# We use pkill with -i for case-insensitive and -f for full command line match
if pkill -if "monitor.py"; then
    echo "🛑 Monitor bot stopped."
else
    echo "⚠️ No running monitor bot found."
fi

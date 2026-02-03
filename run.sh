#!/bin/bash

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run the bot in background and redirect output to monitor.log
# using -u for unbuffered output to see logs immediately
nohup python -u monitor.py > monitor.log 2>&1 &

echo "🚀 Monitor bot started in background."
echo "📝 Logs are being written to monitor.log"
echo "🔢 Process ID: $!"

#!/bin/bash

# Export environment variables for cron
printenv | grep -v "no_proxy" >> /etc/environment

# Start the cron service
service cron start

# Execute initialization pipeline
python3 main.py init

# Start the HTTP server
echo "Starting FastAPI..."
exec python3 -m uvicorn core.api:app --host 0.0.0.0 --port 8000
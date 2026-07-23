#!/bin/bash

# Export environment variables for cron
printenv | grep -v "no_proxy" >> /etc/environment

# Start the cron service
service cron start

# Execute initialization pipeline
# Set DUMPS_DIR=/path/to/nq/files to skip the scraper and index N-Quads dump files directly
INIT_ARGS="init"
if [ -n "${DUMPS_DIR:-}" ]; then
    INIT_ARGS="$INIT_ARGS --with-dumps $DUMPS_DIR"
    echo "DUMPS_DIR=$DUMPS_DIR: skipping scraper, indexing N-Quads dump files directly"
fi
python3 main.py $INIT_ARGS

# Stream QLever HTTP logs into container stdout so docker logs shows incoming SPARQL calls
(
    LOG_FILE="/app/qlever/data_vlaanderen_endpoint.server-log.txt"
    while [ ! -f "$LOG_FILE" ]; do sleep 1; done
    tail -n0 -F "$LOG_FILE" >> /proc/1/fd/1 2>> /proc/1/fd/2
) &

# Start the HTTP server
echo "Starting FastAPI..."
exec python3 -m uvicorn core.api:app --host 0.0.0.0 --port 8000
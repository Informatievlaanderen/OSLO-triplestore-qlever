#!/bin/bash

# Export environment variables for cron
printenv | grep -v "no_proxy" >> /etc/environment

# Start the cron service
service cron start

# Execute initialization pipeline
# Set WITH_DUMPS=1 to skip the scraper and use N-Quads dump files only
INIT_ARGS="init"
if [ "${WITH_DUMPS:-0}" = "1" ]; then
    INIT_ARGS="$INIT_ARGS --with-dumps"
    echo "WITH_DUMPS=1: skipping scraper, using N-Quads dump files only"
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
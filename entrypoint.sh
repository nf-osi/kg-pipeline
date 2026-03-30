#!/bin/bash
set -e

# Start nginx health proxy in background
nginx -c /nginx.conf &

# Start QLever in foreground
exec "$@"

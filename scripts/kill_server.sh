#!/usr/bin/env bash
# Stop dev services.
# Usage: kill_server.sh [app|db]   (default: both)

_kill_port() {
    local port=$1 name=$2
    local pids
    pids=$(lsof -ti:"$port" 2>/dev/null)
    if [ -n "$pids" ]; then
        kill $pids && echo "stopped $name (port $port)" || echo "failed to stop $name"
    else
        echo "$name not running"
    fi
}

_stop_db() {
    devenv processes down && echo "stopped postgres" || echo "postgres not running"
}

case "${1:-all}" in
    all)
        _kill_port 8000 uvicorn
        _stop_db
        ;;
    db)
        _stop_db
        ;;
    app)
        _kill_port 8000 uvicorn
        ;;
    *)
        echo "Usage: $0 [app|db]"
        exit 1
        ;;
esac

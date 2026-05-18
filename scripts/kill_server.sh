#!/usr/bin/env bash
# Kill dev services.
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

case "${1:-all}" in
    all)
        _kill_port 8000 uvicorn
        _kill_port 5433 postgres
        ;;
    db)
        _kill_port 5433 postgres
        ;;
    app)
        _kill_port 8000 uvicorn
        ;;
    *)
        echo "Usage: $0 [app|db]"
        exit 1
        ;;
esac

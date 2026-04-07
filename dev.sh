#!/bin/bash
# REX-US — Start all services
# Usage: ./dev.sh

cd /Users/premkalyan/code/REX-US

echo "Starting REX-US..."

# Kill any existing processes
lsof -i :8000 -t 2>/dev/null | xargs kill 2>/dev/null
lsof -i :5173 -t 2>/dev/null | xargs kill 2>/dev/null
sleep 1

# Start database if not running
docker start rexus-db 2>/dev/null
sleep 2

# Start backend
echo "Starting backend on :8000..."
nohup /Users/premkalyan/code/REX-US/backend/.venv/bin/python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 > /tmp/rexus-backend.log 2>&1 &

# Start frontend
echo "Starting frontend on :5173..."
cd /Users/premkalyan/code/REX-US/frontend
nohup npx vite --host > /tmp/rexus-frontend.log 2>&1 &
cd /Users/premkalyan/code/REX-US

sleep 4

# Health check
if curl -s http://localhost:8000/health | grep -q "healthy"; then
    echo "Backend: OK"
else
    echo "Backend: FAILED — check /tmp/rexus-backend.log"
fi

if curl -s http://localhost:5173/ | grep -q "doctype"; then
    echo "Frontend: OK"
else
    echo "Frontend: FAILED — check /tmp/rexus-frontend.log"
fi

echo ""
echo "Open http://localhost:5173 in your browser"
echo "To share via ngrok: ngrok http 5173"

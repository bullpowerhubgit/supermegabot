#!/bin/bash

# SuperMegaBot System Startup Script
# Starts all components of the complete system

echo "🚀 Starting SuperMegaBot System..."
echo "=================================="

# Set environment variables
export NODE_ENV=production
export REDIS_URL=${REDIS_URL:-"redis://localhost:6379"}
export GOOGLE_ANALYTICS_MEASUREMENT_ID=${GOOGLE_ANALYTICS_MEASUREMENT_ID:-"G-XXXXXXXXXX"}
export GOOGLE_ANALYTICS_API_SECRET=${GOOGLE_ANALYTICS_API_SECRET:-"your-secret"}
export KLAVIYO_API_KEY=${KLAVIYO_API_KEY:-"pk_your_klaviyo_key"}
export GOOGLE_AI_API_KEY=${GOOGLE_AI_API_KEY:-"your-google-ai-key"}

# Check required directories
echo "📁 Checking directories..."
mkdir -p logs
mkdir -p temp
mkdir -p backups

# Start Redis (if not running)
echo "🔴 Starting Redis..."
if pgrep redis-server > /dev/null; then
    echo "✅ Redis is already running"
else
    redis-server --daemonize yes --port 6379 --logfile logs/redis.log
    echo "✅ Redis started"
fi

# Start Node.js backend
echo "🟢 Starting Node.js Backend..."
cd my-shop/backend
npm install --production > /dev/null 2>&1
npm run build > /dev/null 2>&1
node dist/index.js > ../../logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "✅ Backend started (PID: $BACKEND_PID)"

# Start Frontend
echo "🔵 Starting Frontend..."
cd ../frontend
npm install --production > /dev/null 2>&1
npm run build > /dev/null 2>&1
npm run preview --port 3000 > ../../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "✅ Frontend started (PID: $FRONTEND_PID)"

# Start Analytics Service
echo "📊 Starting Analytics Service..."
cd ../../
node services/analytics-service.js > logs/analytics.log 2>&1 &
ANALYTICS_PID=$!
echo "✅ Analytics Service started (PID: $ANALYTICS_PID)"

# Start Klaviyo Service
echo "📧 Starting Klaviyo Service..."
node services/klaviyo-service.js > logs/klaviyo.log 2>&1 &
KLAVIYO_PID=$!
echo "✅ Klaviyo Service started (PID: $KLAVIYO_PID)"

# Start GenAI Service
echo "🤖 Starting GenAI Service..."
node services/genai-service.js > logs/genai.log 2>&1 &
GENAI_PID=$!
echo "✅ GenAI Service started (PID: $GENAI_PID)"

# Start Marketing Automation Engine
echo "📈 Starting Marketing Automation Engine..."
node marketing-automation-engine.js > logs/marketing.log 2>&1 &
MARKETING_PID=$!
echo "✅ Marketing Automation Engine started (PID: $MARKETING_PID)"

# Start Mega Server (main orchestrator)
echo "🎮 Starting Mega Server..."
node mega-server.py > logs/mega-server.log 2>&1 &
MEGA_PID=$!
echo "✅ Mega Server started (PID: $MEGA_PID)"

# Start Cloud Function
echo "☁️ Starting Cloud Function..."
cd gcp-cloud-function
npm install --production > /dev/null 2>&1
functions-framework --target=index --port=8080 > ../logs/cloud-function.log 2>&1 &
CLOUD_PID=$!
echo "✅ Cloud Function started (PID: $CLOUD_PID)"

# Save PIDs for cleanup
cd ../
echo "$BACKEND_PID" > pids/backend.pid
echo "$FRONTEND_PID" > pids/frontend.pid
echo "$ANALYTICS_PID" > pids/analytics.pid
echo "$KLAVIYO_PID" > pids/klaviyo.pid
echo "$GENAI_PID" > pids/genai.pid
echo "$MARKETING_PID" > pids/marketing.pid
echo "$MEGA_PID" > pids/mega-server.pid
echo "$CLOUD_PID" > pids/cloud-function.pid

echo ""
echo "🎉 SuperMegaBot System Started Successfully!"
echo "=========================================="
echo "Frontend: http://localhost:3000"
echo "Backend API: http://localhost:8000"
echo "Cloud Function: http://localhost:8080"
echo "Analytics: http://localhost:8000/analytics"
echo "Klaviyo Service: http://localhost:8001"
echo "GenAI Service: http://localhost:8002"
echo ""
echo "📋 Running Services:"
echo "✅ Node.js Backend (PID: $BACKEND_PID)"
echo "✅ Frontend (PID: $FRONTEND_PID)"
echo "✅ Analytics Service (PID: $ANALYTICS_PID)"
echo "✅ Klaviyo Service (PID: $KLAVIYO_PID)"
echo "✅ GenAI Service (PID: $GENAI_PID)"
echo "✅ Marketing Automation (PID: $MARKETING_PID)"
echo "✅ Mega Server (PID: $MEGA_PID)"
echo "✅ Cloud Function (PID: $CLOUD_PID)"
echo ""
echo "📝 Logs are available in the 'logs/' directory"
echo "🛑 To stop all services, run: ./stop-system.sh"
echo ""
echo "🔍 Health Check in 5 seconds..."
sleep 5

# Check if services are running
check_service() {
    local pid=$1
    local name=$2
    if ps -p $pid > /dev/null; then
        echo "✅ $name is running"
    else
        echo "❌ $name failed to start"
    fi
}

check_service $BACKEND_PID "Backend"
check_service $FRONTEND_PID "Frontend"
check_service $ANALYTICS_PID "Analytics Service"
check_service $KLAVIYO_PID "Klaviyo Service"
check_service $GENAI_PID "GenAI Service"
check_service $MARKETING_PID "Marketing Automation"
check_service $MEGA_PID "Mega Server"
check_service $CLOUD_PID "Cloud Function"

echo ""
echo "🚀 System is ready! Access your SuperMegaBot at http://localhost:3000"

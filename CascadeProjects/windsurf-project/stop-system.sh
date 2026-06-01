#!/bin/bash

# SuperMegaBot System Stop Script
# Stops all running components gracefully

echo "🛑 Stopping SuperMegaBot System..."
echo "================================="

# Function to stop service by PID file
stop_service() {
    local pid_file=$1
    local service_name=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            echo "🛑 Stopping $service_name (PID: $pid)..."
            kill -TERM $pid
            sleep 2
            
            # Force kill if still running
            if ps -p $pid > /dev/null 2>&1; then
                echo "⚡ Force stopping $service_name..."
                kill -KILL $pid
            fi
            
            echo "✅ $service_name stopped"
        else
            echo "⚠️ $service_name was not running"
        fi
        
        rm -f "$pid_file"
    else
        echo "⚠️ No PID file found for $service_name"
    fi
}

# Stop all services
stop_service "pids/backend.pid" "Backend"
stop_service "pids/frontend.pid" "Frontend"
stop_service "pids/analytics.pid" "Analytics Service"
stop_service "pids/klaviyo.pid" "Klaviyo Service"
stop_service "pids/genai.pid" "GenAI Service"
stop_service "pids/marketing.pid" "Marketing Automation"
stop_service "pids/mega-server.pid" "Mega Server"
stop_service "pids/cloud-function.pid" "Cloud Function"

# Stop Redis if started by this script
if pgrep redis-server > /dev/null; then
    echo "🛑 Stopping Redis..."
    redis-cli shutdown
    echo "✅ Redis stopped"
fi

# Clean up any remaining processes
echo "🧹 Cleaning up remaining processes..."
pkill -f "node.*analytics-service"
pkill -f "node.*klaviyo-service"
pkill -f "node.*genai-service"
pkill -f "node.*marketing-automation"
pkill -f "node.*mega-server"
pkill -f "functions-framework"

echo ""
echo "✅ SuperMegaBot System Stopped Successfully!"
echo "=========================================="
echo "All services have been stopped gracefully."
echo "📝 Logs are still available in the 'logs/' directory"

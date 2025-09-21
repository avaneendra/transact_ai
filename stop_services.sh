#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to kill process by port
kill_port() {
    local port=$1
    local service_name=$2
    if lsof -ti:$port > /dev/null; then
        echo -e "${YELLOW}Stopping $service_name on port $port...${NC}"
        lsof -ti:$port | xargs kill -9 2>/dev/null
        sleep 1
        if ! lsof -ti:$port > /dev/null; then
            echo -e "${GREEN}$service_name stopped successfully${NC}"
        else
            echo -e "${RED}Failed to stop $service_name${NC}"
        fi
    else
        echo -e "${GREEN}$service_name not running on port $port${NC}"
    fi
}

# Function to kill process by PID file
kill_pid_file() {
    local pid_file=$1
    local service_name=$2
    if [ -f $pid_file ]; then
        echo -e "${YELLOW}Stopping $service_name using PID file...${NC}"
        kill -9 $(cat $pid_file) 2>/dev/null
        rm $pid_file
        echo -e "${GREEN}$service_name stopped${NC}"
    fi
}

echo -e "${YELLOW}Stopping all services...${NC}"

# Stop services by PID files
kill_pid_file ".order_pid" "Order Agent MCP"
kill_pid_file ".payment_server_pid" "Payment Server"
kill_pid_file ".payment_ai_pid" "Payment AI Agent"
kill_pid_file ".streamlit_pid" "Streamlit app"

# Stop services by port
kill_port 8001 "Order Agent MCP"
kill_port 8002 "Payment Server"
kill_port 8003 "Payment AI Agent"
kill_port 8501 "Streamlit UI"

# Double check no lingering processes
echo -e "${YELLOW}Checking for any lingering processes...${NC}"
pkill -f "uvicorn order_agent_mcp:app" 2>/dev/null
pkill -f "uvicorn payment_server:app" 2>/dev/null
pkill -f "uvicorn payment_ai_agent:app" 2>/dev/null
pkill -f "streamlit run orchestrator.py" 2>/dev/null

# Clean up any stale PID files
rm -f .order_pid .payment_server_pid .payment_ai_pid .streamlit_pid

echo -e "${GREEN}All services stopped successfully!${NC}"

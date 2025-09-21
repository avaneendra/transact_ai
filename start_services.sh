#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if a port is available
check_port() {
    if lsof -i :$1 > /dev/null; then
        echo -e "${RED}Port $1 is already in use. Please free up this port first.${NC}"
        return 1
    fi
    return 0
}

# Function to wait for a service to be ready
wait_for_service() {
    local port=$1
    local service=$2
    local max_attempts=30
    local attempt=1

    echo -e "${YELLOW}Waiting for $service to start on port $port...${NC}"
    
    while ! curl -s http://localhost:$port/docs > /dev/null; do
        if [ $attempt -gt $max_attempts ]; then
            echo -e "${RED}$service failed to start after $max_attempts attempts${NC}"
            return 1
        fi
        sleep 1
        attempt=$((attempt + 1))
    done
    
    echo -e "${GREEN}$service is ready!${NC}"
    return 0
}

# Load environment variables
if [ -f .env ]; then
    echo -e "${GREEN}Loading environment variables from .env${NC}"
    export $(cat .env | grep -v '^#' | xargs)
else
    echo -e "${RED}No .env file found. Please create one with your GOOGLE_API_KEY${NC}"
    exit 1
fi

# Check if GOOGLE_API_KEY is set
if [ -z "$GOOGLE_API_KEY" ]; then
    echo -e "${RED}GOOGLE_API_KEY not found in .env file${NC}"
    exit 1
fi

# Check if we're in a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    if [ -d "triage_env" ]; then
        echo -e "${YELLOW}Activating virtual environment...${NC}"
        source triage_env/bin/activate
    else
        echo -e "${RED}Virtual environment not found. Please create and activate it first.${NC}"
        exit 1
    fi
fi

# Kill any existing processes on our ports
kill_port() {
    local port=$1
    if lsof -ti:$port > /dev/null; then
        echo -e "${YELLOW}Killing process on port $port...${NC}"
        lsof -ti:$port | xargs kill -9 2>/dev/null
        sleep 1  # Give the process time to die
    fi
}

# Clean up any existing processes
echo -e "${YELLOW}Cleaning up any existing processes...${NC}"
kill_port 8001
kill_port 8002
kill_port 8003
kill_port 8501

# Remove any stale PID files
rm -f .order_pid .payment_server_pid .payment_ai_pid .streamlit_pid

# Check all ports are now free
echo -e "${YELLOW}Verifying ports are free...${NC}"
check_port 8001 || exit 1
check_port 8002 || exit 1
check_port 8003 || exit 1
check_port 8501 || exit 1  # Streamlit's default port

# Start Order Agent MCP (port 8001)
echo -e "${YELLOW}Starting Order Agent MCP...${NC}"
uvicorn order_agent_mcp:app --port 8001 &
ORDER_PID=$!
wait_for_service 8001 "Order Agent MCP" || exit 1

# Start Payment Server (port 8002)
echo -e "${YELLOW}Starting Payment Server...${NC}"
uvicorn payment_server:app --port 8002 &
PAYMENT_SERVER_PID=$!
wait_for_service 8002 "Payment Server" || exit 1

# Start Payment AI Agent (port 8003)
echo -e "${YELLOW}Starting Payment AI Agent...${NC}"
uvicorn payment_ai_agent:app --port 8003 &
PAYMENT_AI_PID=$!
wait_for_service 8003 "Payment AI Agent" || exit 1

# Start Streamlit app
echo -e "${YELLOW}Starting Streamlit app...${NC}"
streamlit run orchestrator.py &
STREAMLIT_PID=$!

# Save PIDs for cleanup
echo $ORDER_PID > .order_pid
echo $PAYMENT_SERVER_PID > .payment_server_pid
echo $PAYMENT_AI_PID > .payment_ai_pid
echo $STREAMLIT_PID > .streamlit_pid

echo -e "${GREEN}All services started successfully!${NC}"
echo -e "${GREEN}Open http://localhost:8501 in your browser to access the app${NC}"

# Function to cleanup on script termination
cleanup() {
    echo -e "\n${YELLOW}Shutting down services...${NC}"
    kill $(cat .order_pid) 2>/dev/null
    kill $(cat .payment_server_pid) 2>/dev/null
    kill $(cat .payment_ai_pid) 2>/dev/null
    kill $(cat .streamlit_pid) 2>/dev/null
    rm -f .order_pid .payment_server_pid .payment_ai_pid .streamlit_pid
    echo -e "${GREEN}All services stopped${NC}"
}

# Register cleanup function
trap cleanup EXIT

# Keep script running to maintain services
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
wait

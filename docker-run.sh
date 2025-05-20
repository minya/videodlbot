#!/bin/bash

# Docker management script for Video Downloader Telegram Bot
# This script handles common Docker operations for the bot

# Set color variables
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to show help message
show_help() {
    echo -e "${YELLOW}Video Downloader Bot Docker Manager${NC}"
    echo 
    echo "Usage: $0 [command]"
    echo
    echo "Commands:"
    echo "  build       Build the Docker image"
    echo "  start       Start the bot container (builds if image doesn't exist)"
    echo "  stop        Stop the bot container"
    echo "  restart     Restart the bot container"
    echo "  logs        View container logs (press Ctrl+C to exit)"
    echo "  status      Check if the container is running"
    echo "  cleanup     Remove unused Docker resources"
    echo "  help        Show this help message"
    echo
    echo "Example: $0 start"
    echo
    echo "For more information, see README.md"
}

# Function to check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed or not in PATH${NC}"
        echo "Please install Docker first: https://docs.docker.com/get-docker/"
        exit 1
    fi
}

# Function to check if docker-compose is installed
check_docker_compose() {
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}Error: docker-compose is not installed or not in PATH${NC}"
        echo "Please install docker-compose first: https://docs.docker.com/compose/install/"
        exit 1
    fi
}

# Function to check if .env file exists and doesn't have default token
check_env_file() {
    if [ ! -f .env ]; then
        echo -e "${YELLOW}Warning: .env file not found.${NC}"
        echo "Creating from .env template..."
        cp .env.docker.sample .env
        echo -e "${YELLOW}Please edit the .env file to add your Telegram Bot Token.${NC}"
        exit 1
    fi
    
    if grep -q "your_telegram_bot_token_here" .env; then
        echo -e "${RED}Error: Default Telegram Bot Token detected in .env file.${NC}"
        echo "Please edit the .env file and add your actual Telegram Bot Token."
        exit 1
    fi
    
    if grep -q "your_telegram_user_id_here" .env; then
        echo -e "${RED}Error: Default Telegram User ID detected in .env file.${NC}"
        echo "Please edit the .env file and add your actual Telegram User ID."
        exit 1
    fi
}

# Function to build Docker image
build_image() {
    echo -e "${YELLOW}Building Docker image...${NC}"
    docker-compose build
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Build successful!${NC}"
    else
        echo -e "${RED}Build failed!${NC}"
        exit 1
    fi
}

# Function to start container
start_container() {
    check_env_file
    
    # Check if image exists, if not build it
    if [ -z "$(docker images -q videodlbot_videodlbot 2>/dev/null)" ]; then
        echo -e "${YELLOW}Docker image not found. Building first...${NC}"
        build_image
    fi
    
    echo -e "${YELLOW}Starting container...${NC}"
    docker-compose up -d
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Container started successfully!${NC}"
        echo -e "Use '$0 logs' to view logs."
    else
        echo -e "${RED}Failed to start container!${NC}"
        exit 1
    fi
}

# Function to stop container
stop_container() {
    echo -e "${YELLOW}Stopping container...${NC}"
    docker-compose down
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Container stopped successfully!${NC}"
    else
        echo -e "${RED}Failed to stop container!${NC}"
        exit 1
    fi
}

# Function to restart container
restart_container() {
    echo -e "${YELLOW}Restarting container...${NC}"
    docker-compose restart
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Container restarted successfully!${NC}"
    else
        echo -e "${RED}Failed to restart container!${NC}"
        exit 1
    fi
}

# Function to view logs
view_logs() {
    echo -e "${YELLOW}Showing container logs (press Ctrl+C to exit)...${NC}"
    docker-compose logs -f
}

# Function to check container status
check_status() {
    if [ "$(docker ps -q -f name=videodlbot)" ]; then
        echo -e "${GREEN}Container is running!${NC}"
        docker ps -f name=videodlbot
    else
        echo -e "${RED}Container is not running!${NC}"
        exit 1
    fi
}

# Function to clean up Docker resources
cleanup_resources() {
    echo -e "${YELLOW}Removing unused Docker resources...${NC}"
    docker system prune -f
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Cleanup completed successfully!${NC}"
    else
        echo -e "${RED}Cleanup failed!${NC}"
        exit 1
    fi
}

# Main script logic
check_docker
check_docker_compose

case "$1" in
    build)
        build_image
        ;;
    start)
        start_container
        ;;
    stop)
        stop_container
        ;;
    restart)
        restart_container
        ;;
    logs)
        view_logs
        ;;
    status)
        check_status
        ;;
    cleanup)
        cleanup_resources
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        show_help
        exit 1
        ;;
esac

exit 0
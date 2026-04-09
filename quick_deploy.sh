#!/bin/bash
# quick_deploy.sh - One-command deployment for Esploro Citation Bot
#
# Usage:
#   ./quick_deploy.sh systemd     # Deploy with systemd
#   ./quick_deploy.sh local       # Run locally
#   ./quick_deploy.sh validate    # Only validate environment

set -e

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
COLOR_BLUE='\033[0;34m'
COLOR_RESET='\033[0m'

print_header() {
    echo -e "${COLOR_BLUE}============================================${COLOR_RESET}"
    echo -e "${COLOR_BLUE}$1${COLOR_RESET}"
    echo -e "${COLOR_BLUE}============================================${COLOR_RESET}"
}

print_success() {
    echo -e "${COLOR_GREEN}✓ $1${COLOR_RESET}"
}

print_warning() {
    echo -e "${COLOR_YELLOW}⚠ $1${COLOR_RESET}"
}

print_error() {
    echo -e "${COLOR_RED}✗ $1${COLOR_RESET}"
}

validate_environment() {
    print_header "Validating Environment"

    # Check if .env exists
    if [ ! -f ".env" ]; then
        print_error ".env file not found"
        print_warning "Copy docs/ENV_EXAMPLE.md to .env and configure it"
        exit 1
    fi

    # Run validation script
    if [ -f "deployment/validate_env.py" ]; then
        python3 deployment/validate_env.py
        if [ $? -ne 0 ]; then
            print_error "Environment validation failed"
            exit 1
        fi
    else
        print_warning "Validation script not found, skipping detailed checks"
    fi

    print_success "Environment validated successfully"
}

deploy_systemd() {
    print_header "Deploying with systemd"

    # Check if running as root or with sudo
    if [ "$EUID" -ne 0 ]; then
        print_error "Please run with sudo for systemd deployment"
        exit 1
    fi

    # Validate environment first
    validate_environment

    # Create service user if doesn't exist
    if ! id "espbot" &>/dev/null; then
        print_header "Creating Service User"
        useradd -r -m -s /bin/bash espbot
        print_success "Created user: espbot"
    fi

    # Copy files to /opt if not already there
    if [ "$PWD" != "/opt/esploro-bot" ]; then
        print_header "Copying to /opt/esploro-bot"
        mkdir -p /opt/esploro-bot
        cp -r . /opt/esploro-bot/
        chown -R espbot:espbot /opt/esploro-bot
        print_success "Files copied to /opt/esploro-bot"
    fi

    # Install Python dependencies
    print_header "Installing Dependencies"
    cd /opt/esploro-bot
    sudo -u espbot python3 -m venv .venv || true
    sudo -u espbot .venv/bin/pip install -r requirements.txt
    sudo -u espbot .venv/bin/python -m playwright install chromium
    print_success "Dependencies installed"

    # Install systemd service
    print_header "Installing systemd Service"
    cp deployment/esploro-bot.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable esploro-bot
    systemctl start esploro-bot

    print_success "systemd deployment complete!"
    echo ""
    echo "View logs: sudo journalctl -u esploro-bot -f"
    echo "Status: sudo systemctl status esploro-bot"
    echo "Restart: sudo systemctl restart esploro-bot"
}

deploy_local() {
    print_header "Starting Local Deployment"

    # Validate environment first
    validate_environment

    # Check if start script exists
    if [ ! -f "start_smart_batch.sh" ]; then
        print_error "start_smart_batch.sh not found"
        exit 1
    fi

    # Run the start script
    print_header "Starting Bot"
    ./start_smart_batch.sh
}

show_usage() {
    echo "Usage: $0 [systemd|local|validate]"
    echo ""
    echo "Commands:"
    echo "  systemd    - Deploy with systemd (Linux servers)"
    echo "  local      - Run locally with start_smart_batch.sh"
    echo "  validate   - Only validate environment"
    echo ""
    echo "Examples:"
    echo "  sudo $0 systemd        # Install as system service"
    echo "  $0 local               # Run in current terminal"
    echo ""
    echo "For more information, see:"
    echo "  - PRODUCTION.md"
    echo "  - deployment/DEPLOYMENT.md"
}

# Main script
case "${1:-}" in
    systemd)
        deploy_systemd
        ;;
    local)
        deploy_local
        ;;
    validate)
        validate_environment
        ;;
    *)
        show_usage
        exit 1
        ;;
esac

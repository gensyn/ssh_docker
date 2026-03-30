#!/usr/bin/env bash
# run_playwright_tests.sh
#
# Runs the Playwright E2E test suite in a fully isolated Docker environment.
# No local Python environment or browser installation is required.
#
# The suite spins up Home Assistant, a mock Docker host, and the Playwright
# test runner via docker compose, then tears everything down on exit.
#
# Usage:
#   ./run_playwright_tests.sh

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[PASS]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[FAIL]${NC}  $*"; }
header()  { echo -e "\n${BOLD}$*${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yaml"

command_exists() { command -v "$1" &>/dev/null; }

# ── Docker installation / update ─────────────────────────────────────────────
install_docker() {
    if command_exists docker; then
        info "Docker is already installed: $(sudo docker --version)"
        info "Checking for Docker updates…"
        if command_exists apt-get; then
            sudo apt-get update -qq \
                && sudo apt-get install --only-upgrade -y \
                    docker-ce docker-ce-cli containerd.io docker-compose-plugin \
                || true
        elif command_exists yum; then
            sudo yum update -y \
                docker-ce docker-ce-cli containerd.io docker-compose-plugin \
                || true
        else
            warn "Cannot automatically update Docker on this platform; please update it manually."
        fi
        info "Docker version after update check: $(sudo docker --version)"
        return 0
    fi

    header "Installing Docker…"
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER" || true
    warn "Docker installed. You may need to run 'newgrp docker' or re-login for group membership to take effect."
}

# ── act installation / update ─────────────────────────────────────────────────
install_act() {
    if command_exists act; then
        local current_version latest_version
        current_version="$(act --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
        latest_version="$(curl -fsSL https://api.github.com/repos/nektos/act/releases/latest 2>/dev/null \
            | grep '"tag_name"' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"

        if [[ -z "$current_version" ]] || [[ -z "$latest_version" ]]; then
            [[ -z "$current_version" ]] && warn "Could not determine the installed act version; skipping update check."
            [[ -z "$latest_version" ]]  && warn "Could not determine the latest act version (network issue?); skipping update check."
            info "act is already installed: $(act --version)"
            return 0
        fi

        if [[ "$current_version" == "$latest_version" ]]; then
            info "act is already up to date: $(act --version)"
            return 0
        fi

        header "Updating act from ${current_version} to ${latest_version}…"
        curl -fsSL https://raw.githubusercontent.com/nektos/act/master/install.sh \
            | sudo bash -s -- -b /usr/local/bin
        return 0
    fi

    header "Installing act…"
    curl -fsSL https://raw.githubusercontent.com/nektos/act/master/install.sh \
        | sudo bash -s -- -b /usr/local/bin
}

# ── Docker daemon check ───────────────────────────────────────────────────────
ensure_docker_running() {
    if sudo docker info &>/dev/null; then
        return 0
    fi

    warn "Docker daemon is not running – attempting to start it…"
    if command_exists systemctl; then
        sudo systemctl start docker
    else
        sudo service docker start
    fi
    sleep 3  # give the daemon a moment to become ready before re-checking

    if ! sudo docker info &>/dev/null; then
        error "Docker daemon is still not running. Please start Docker manually and re-run this script."
        exit 1
    fi
}

# ── Resolve docker compose command ───────────────────────────────────────────
get_compose_cmd() {
    if command -v docker &>/dev/null && sudo docker compose version &>/dev/null 2>&1; then
        echo "sudo docker compose"
    else
        error "docker compose is not available. Please install Docker with the Compose plugin."
        exit 1
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    if [[ $# -gt 0 ]]; then
        error "This script takes no arguments."
        echo "Usage: $0"
        exit 1
    fi

    if [[ ! -f "$COMPOSE_FILE" ]]; then
        error "docker-compose.yaml not found at $COMPOSE_FILE"
        exit 1
    fi

    header "════════════════════════════════════════════════════"
    header " Playwright E2E tests (docker compose)"
    header "════════════════════════════════════════════════════"

    install_docker
    install_act
    ensure_docker_running

    local compose_cmd
    compose_cmd="$(get_compose_cmd)"

    info "Building Docker images…"
    $compose_cmd -f "$COMPOSE_FILE" build

    info "Running test container (this may take several minutes on first run)…"
    local exit_code=0
    $compose_cmd -f "$COMPOSE_FILE" run --rm playwright-tests || exit_code=$?

    info "Stopping services…"
    $compose_cmd -f "$COMPOSE_FILE" down -v || true

    if [[ $exit_code -eq 0 ]]; then
        echo ""
        success "All Playwright E2E tests passed."
        exit 0
    else
        echo ""
        error "Playwright E2E tests failed (exit code ${exit_code})."
        exit "${exit_code}"
    fi
}

main "$@"

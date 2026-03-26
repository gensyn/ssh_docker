#!/bin/sh
# docker-host-entrypoint.sh — Initialises mock Docker state and starts sshd.
#
# Creates two pre-populated "containers" (test-app, test-app-2) that the
# Playwright tests can interact with, then hands control to sshd so the
# SSH Docker integration can connect and run docker commands.

set -e

DOCKER_STATE_DIR="/var/mock-docker"
mkdir -p "$DOCKER_STATE_DIR"

# ── Initialise mock containers ────────────────────────────────────────────────
for name in test-app test-app-2; do
    mkdir -p "$DOCKER_STATE_DIR/$name"
    echo "running"                                          > "$DOCKER_STATE_DIR/$name/state"
    echo "2024-01-01T12:00:00.000000000Z"                  > "$DOCKER_STATE_DIR/$name/created"
    echo "alpine:3.19"                                     > "$DOCKER_STATE_DIR/$name/image"
    echo "sha256:abc123def456abc123def456abc123def456abc123def456abc123def456abc123" \
                                                           > "$DOCKER_STATE_DIR/$name/image_id"
done

# Give the SSH user (foo) ownership of all state files so it can update them
# when running docker stop/start/restart commands via the mock CLI.
# Without this the files are owned by root (644) and the write silently fails,
# causing mock commands to exit 0 while leaving the state unchanged.
chown -R foo:foo "$DOCKER_STATE_DIR"

printf '[docker-host] Mock Docker state initialised (containers: test-app, test-app-2)\n'

# ── Start SSH daemon in the foreground ────────────────────────────────────────
printf '[docker-host] Starting sshd...\n'
exec /usr/sbin/sshd -D

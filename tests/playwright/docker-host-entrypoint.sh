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

# Make state files and subdirectories world-writable so the SSH user (foo)
# can update them when running docker stop/start/restart commands via the
# mock CLI.  We use chmod rather than chown so root retains ownership (which
# avoids any sshd or file-system ownership checks that chown could trigger).
# The parent directory already has 777 from the Dockerfile; this extends
# write permission to the subdirectories and files inside it.
chmod -R a+w "$DOCKER_STATE_DIR"

printf '[docker-host] Mock Docker state initialised (containers: test-app, test-app-2)\n'

# ── Start SSH daemon in the foreground ────────────────────────────────────────
printf '[docker-host] Starting sshd...\n'
exec /usr/sbin/sshd -D

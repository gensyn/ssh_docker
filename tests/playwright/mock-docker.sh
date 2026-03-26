#!/bin/sh
# mock-docker.sh — Simulates a Docker CLI for SSH Docker Playwright E2E tests.
#
# Container state is stored under /var/mock-docker/<name>/ as plain text files:
#   state     — "running" | "exited" | "paused" etc.
#   created   — ISO-8601 timestamp string
#   image     — image name (e.g. "alpine:3.19")
#   image_id  — full image ID (sha256:...)
#
# The script is installed as /usr/local/bin/docker so that ssh_docker's
# coordinator can call it transparently over SSH.

DOCKER_STATE_DIR="/var/mock-docker"
mkdir -p "$DOCKER_STATE_DIR"

container_exists() {
    [ -d "$DOCKER_STATE_DIR/$1" ]
}

CMD="$1"
shift

case "$CMD" in

    # ── docker inspect ────────────────────────────────────────────────────────
    "inspect")
        container=""
        format=""
        while [ $# -gt 0 ]; do
            case "$1" in
                --format) format="$2"; shift 2 ;;
                *)        container="$1"; shift ;;
            esac
        done

        if ! container_exists "$container"; then
            printf 'Error response from daemon: No such container: %s\n' "$container" >&2
            exit 1
        fi

        state=$(cat "$DOCKER_STATE_DIR/$container/state"    2>/dev/null || echo "running")
        created=$(cat "$DOCKER_STATE_DIR/$container/created"  2>/dev/null || echo "2024-01-01T12:00:00.000000000Z")
        image=$(cat "$DOCKER_STATE_DIR/$container/image"    2>/dev/null || echo "alpine:3.19")
        image_id=$(cat "$DOCKER_STATE_DIR/$container/image_id" 2>/dev/null || echo "sha256:abc123def456abc123def456abc123def456abc123def456abc123def456abc123")

        # Replace Go-template placeholders used by the coordinator.
        result="$format"
        result=$(printf '%s' "$result" | sed "s|{{.State.Status}}|$state|g")
        result=$(printf '%s' "$result" | sed "s|{{.Created}}|$created|g")
        result=$(printf '%s' "$result" | sed "s|{{.Config.Image}}|$image|g")
        result=$(printf '%s' "$result" | sed "s|{{.Image}}|$image_id|g")
        printf '%s\n' "$result"
        ;;

    # ── docker ps ─────────────────────────────────────────────────────────────
    "ps")
        show_all=false
        format=""
        quiet=false
        filter=""
        while [ $# -gt 0 ]; do
            case "$1" in
                -a)       show_all=true; shift ;;
                --format) format="$2"; shift 2 ;;
                -q)       quiet=true; shift ;;
                --filter) filter="$2"; shift 2 ;;
                *)        shift ;;
            esac
        done

        for dir in "$DOCKER_STATE_DIR"/*/; do
            [ -d "$dir" ] || continue
            name=$(basename "$dir")
            state=$(cat "$dir/state" 2>/dev/null || echo "exited")

            if [ "$show_all" = "false" ] && [ "$state" != "running" ]; then
                continue
            fi

            if [ -n "$format" ]; then
                result="$format"
                result=$(printf '%s' "$result" | sed "s|{{.Names}}|$name|g")
                printf '%s\n' "$result"
            elif [ "$quiet" = "true" ]; then
                printf '%s\n' "$name"
            else
                printf '%s\n' "$name"
            fi
        done
        ;;

    # ── docker restart ────────────────────────────────────────────────────────
    "restart")
        container="$1"
        if ! container_exists "$container"; then
            printf 'Error response from daemon: No such container: %s\n' "$container" >&2
            exit 1
        fi
        echo "running" > "$DOCKER_STATE_DIR/$container/state"
        printf '%s\n' "$container"
        ;;

    # ── docker stop ───────────────────────────────────────────────────────────
    "stop")
        container="$1"
        if ! container_exists "$container"; then
            printf 'Error response from daemon: No such container: %s\n' "$container" >&2
            exit 1
        fi
        echo "exited" > "$DOCKER_STATE_DIR/$container/state"
        printf '%s\n' "$container"
        ;;

    # ── docker start ──────────────────────────────────────────────────────────
    "start")
        container="$1"
        if ! container_exists "$container"; then
            printf 'Error response from daemon: No such container: %s\n' "$container" >&2
            exit 1
        fi
        echo "running" > "$DOCKER_STATE_DIR/$container/state"
        printf '%s\n' "$container"
        ;;

    # ── docker rm ─────────────────────────────────────────────────────────────
    "rm")
        # Accept optional -f flag
        if [ "$1" = "-f" ]; then shift; fi
        container="$1"
        if ! container_exists "$container"; then
            printf 'Error response from daemon: No such container: %s\n' "$container" >&2
            exit 1
        fi
        rm -rf "${DOCKER_STATE_DIR:?}/$container"
        printf '%s\n' "$container"
        ;;

    # ── docker logs ───────────────────────────────────────────────────────────
    "logs")
        # Accept optional flags (e.g. parsed in a pipeline with 2>&1 | tail -200)
        container=""
        while [ $# -gt 0 ]; do
            case "$1" in
                --tail|-n|--since|--until) shift 2 ;;
                -f|--follow|--timestamps)  shift ;;
                *)  container="$1"; shift ;;
            esac
        done
        if [ -z "$container" ]; then exit 0; fi
        if ! container_exists "$container"; then
            printf 'Error response from daemon: No such container: %s\n' "$container" >&2
            exit 1
        fi
        printf 'Mock log line 1 for %s\n' "$container"
        printf 'Mock log line 2 for %s\n' "$container"
        printf 'Mock log line 3 for %s\n' "$container"
        ;;

    # ── docker image inspect ──────────────────────────────────────────────────
    "image")
        subcmd="$1"; shift
        if [ "$subcmd" = "inspect" ]; then
            format=""
            while [ $# -gt 0 ]; do
                case "$1" in
                    --format) format="$2"; shift 2 ;;
                    *)        shift ;;
                esac
            done
            # Return a stable mock image ID
            mock_id="sha256:abc123def456abc123def456abc123def456abc123def456abc123def456abc123"
            if [ -n "$format" ]; then
                result=$(printf '%s' "$format" | sed "s|{{.Id}}|$mock_id|g")
                printf '%s\n' "$result"
            else
                printf '%s\n' "$mock_id"
            fi
        fi
        ;;

    # ── docker pull ───────────────────────────────────────────────────────────
    "pull")
        # Silent success — no network access needed
        ;;

    # ── docker info ───────────────────────────────────────────────────────────
    "info")
        printf 'Client: Docker Engine\nServer:\n Server Version: mock-1.0\n'
        ;;

    # ── fallback ──────────────────────────────────────────────────────────────
    *)
        printf 'mock-docker: unknown command: %s\n' "$CMD" >&2
        exit 1
        ;;
esac

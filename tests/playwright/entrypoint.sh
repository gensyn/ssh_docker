#!/usr/bin/env bash
# entrypoint.sh — startup script for the Playwright E2E test-runner container.
#
# 1. Waits for Home Assistant to become reachable.
# 2. Runs the full HA onboarding flow to create the admin user and complete all
#    onboarding steps (if they haven't been completed yet).
# 3. Sets up the SSH Command integration (required by SSH Docker).
# 4. Hands off to pytest.

set -euo pipefail

HA_URL="${HOMEASSISTANT_URL:-http://homeassistant:8123}"
HA_USER="${HA_USERNAME:-admin}"
HA_PASS="${HA_PASSWORD:-admin}"
RESULTS_DIR="/app/playwright-results"

log() { echo "[entrypoint] $*"; }

mkdir -p "${RESULTS_DIR}"

# ── 1. Wait for Home Assistant to respond ────────────────────────────────────
log "Waiting for Home Assistant at ${HA_URL} …"
ATTEMPT=0
MAX_ATTEMPTS=120
until HTTP=$(curl -s -o /dev/null -w "%{http_code}" "${HA_URL}/api/onboarding" 2>/dev/null) && \
      [[ "${HTTP}" =~ ^[2-4][0-9]{2}$ ]]; do
    ATTEMPT=$(( ATTEMPT + 1 ))
    if [[ "${ATTEMPT}" -ge "${MAX_ATTEMPTS}" ]]; then
        log "ERROR: Home Assistant did not become ready after ${MAX_ATTEMPTS} attempts."
        exit 1
    fi
    log "  Attempt ${ATTEMPT}/${MAX_ATTEMPTS} (HTTP ${HTTP:-000}), retrying in 5 s …"
    sleep 5
done
log "Home Assistant is responding."

# ── 2. Onboarding (complete all steps on first start) ─────────────────────────
ONBOARDING=$(curl -sf "${HA_URL}/api/onboarding" 2>/dev/null || echo '[]')

USER_DONE=$(_ONBOARDING="${ONBOARDING}" python3 - <<'PYEOF'
import json, os, sys
try:
    data = json.loads(os.environ.get("_ONBOARDING", "[]"))
    if not isinstance(data, list):
        raise ValueError("unexpected onboarding format")
    print("true" if any(s.get("step") == "user" and s.get("done") for s in data) else "false")
except Exception:
    print("false")
PYEOF
)

AUTH_TOKEN=""

if [[ "${USER_DONE}" == "false" ]]; then
    log "Running HA onboarding — creating admin user '${HA_USER}' …"

    PAYLOAD="{\"client_id\":\"${HA_URL}/\",\"name\":\"Admin\",\"username\":\"${HA_USER}\",\"password\":\"${HA_PASS}\",\"language\":\"en\"}"
    USER_RESPONSE=$(curl -sf -X POST "${HA_URL}/api/onboarding/users" \
        -H "Content-Type: application/json" \
        -d "${PAYLOAD}" 2>&1) || {
        log "WARNING: Onboarding/users request failed. HA may already be fully onboarded."
        USER_RESPONSE=""
    }

    if [[ -n "${USER_RESPONSE}" ]]; then
        AUTH_TOKEN=$(_RESP="${USER_RESPONSE}" HA_URL="${HA_URL}" python3 - <<'PYEOF'
import json, os, sys, urllib.request, urllib.parse

resp = os.environ.get("_RESP", "")
ha_url = os.environ.get("HA_URL", "")

try:
    auth_code = json.loads(resp)["auth_code"]
except Exception:
    print("")
    sys.exit(0)

data = urllib.parse.urlencode({
    "grant_type": "authorization_code",
    "code": auth_code,
    "client_id": ha_url + "/",
}).encode()
req = urllib.request.Request(f"{ha_url}/auth/token", data=data, method="POST")
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print(json.loads(r.read())["access_token"])
except Exception:
    print("")
PYEOF
        )

        if [[ -n "${AUTH_TOKEN}" ]]; then
            for STEP in core_config analytics integration; do
                log "  Completing onboarding step: ${STEP} …"
                curl -sf -X POST "${HA_URL}/api/onboarding/${STEP}" \
                    -H "Authorization: Bearer ${AUTH_TOKEN}" \
                    -H "Content-Type: application/json" \
                    -d '{}' > /dev/null 2>&1 || \
                    log "  WARNING: step '${STEP}' returned an error (may be harmless)."
            done
        fi
    fi

    log "Onboarding complete."
    sleep 10
fi

# ── 3. Obtain an auth token if we don't have one yet ─────────────────────────
if [[ -z "${AUTH_TOKEN}" ]]; then
    log "Obtaining HA auth token …"
    AUTH_TOKEN=$(HA_URL="${HA_URL}" HA_USER="${HA_USER}" HA_PASS="${HA_PASS}" python3 - <<'PYEOF'
import json, os, sys, urllib.request, urllib.parse

ha_url  = os.environ["HA_URL"]
ha_user = os.environ["HA_USER"]
ha_pass = os.environ["HA_PASS"]

def post_json(url, payload):
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

try:
    flow = post_json(f"{ha_url}/auth/login_flow", {
        "client_id": f"{ha_url}/",
        "handler": ["homeassistant", None],
        "redirect_uri": f"{ha_url}/",
    })
    cred = post_json(f"{ha_url}/auth/login_flow/{flow['flow_id']}", {
        "username": ha_user,
        "password": ha_pass,
        "client_id": f"{ha_url}/",
    })
    code = cred["result"]
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": f"{ha_url}/",
    }).encode()
    req = urllib.request.Request(f"{ha_url}/auth/token", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        print(json.loads(r.read())["access_token"])
except Exception as e:
    print("", file=sys.stderr)
    sys.exit(1)
PYEOF
    ) || { log "ERROR: could not obtain HA token."; exit 1; }
fi

log "Auth token obtained."

# ── 4. Set up the SSH Command integration (required by SSH Docker) ────────────
log "Setting up SSH Command integration …"
SSH_CMD_ENTRIES=$(curl -sf "${HA_URL}/api/config/config_entries/entry" \
    -H "Authorization: Bearer ${AUTH_TOKEN}" | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print(sum(1 for e in d if e.get('domain')=='ssh_command'))" 2>/dev/null || echo "0")

if [[ "${SSH_CMD_ENTRIES}" -eq 0 ]]; then
    curl -sf -X POST "${HA_URL}/api/config/config_entries/flow" \
        -H "Authorization: Bearer ${AUTH_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{"handler":"ssh_command"}' > /dev/null && \
        log "SSH Command integration set up." || \
        log "WARNING: SSH Command setup failed (integration may already be loading)."
    sleep 5
else
    log "SSH Command integration already configured."
fi

# ── 5. Run the test suite ─────────────────────────────────────────────────────
log "Starting Playwright E2E test suite …"

cd /app/tests/playwright
exec pytest . \
    --tb=short \
    -v \
    --junitxml="${RESULTS_DIR}/junit.xml" \
    "$@"

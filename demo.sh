#!/bin/bash

set -euo pipefail

NODE_COUNT=${NODE_COUNT:-5}
NODE_API_BASE_HOST=${NODE_API_BASE_HOST:-127.0.0.1}
NODE_API_BASE_PORT=${NODE_API_BASE_PORT:-8000}
NODE_API_PORT_STEP=${NODE_API_PORT_STEP:-1}
NODE_SOCKET_BASE_PORT=${NODE_SOCKET_BASE_PORT:-9000}
NODE_SOCKET_PORT_STEP=${NODE_SOCKET_PORT_STEP:-1}

if (( NODE_COUNT < 5 )); then
    echo "demo.sh need 5 nodes minimum (NODE_COUNT)." >&2
    exit 1
fi

node_api_url() {
    local idx="$1"
    local override_var="NODE${idx}_HOST"
    local override_value="${!override_var-}"

    if [[ -n "${override_value}" ]]; then
        echo "${override_value}"
        return
    fi

    local port=$(( NODE_API_BASE_PORT + (idx - 1) * NODE_API_PORT_STEP ))
    echo "http://${NODE_API_BASE_HOST}:${port}"
}

node_socket_port() {
    local idx="$1"
    local override_var="NODE${idx}_SOCKET_PORT"
    local override_value="${!override_var-}"

    if [[ -n "${override_value}" ]]; then
        echo "${override_value}"
        return
    fi

    echo $(( NODE_SOCKET_BASE_PORT + (idx - 1) * NODE_SOCKET_PORT_STEP ))
}

declare -a NODE_URLS
declare -a NODE_SOCKET_PORTS

for (( idx=1; idx<=NODE_COUNT; idx++ )); do
    NODE_URLS[$idx]="$(node_api_url "${idx}")"
    NODE_SOCKET_PORTS[$idx]="$(node_socket_port "${idx}")"
done

join_payload() {
    local idx="$1"
    printf '{"node_id": %d, "host": "%s", "socket_port": %d}' \
        "${idx}" "${NODE_URLS[$idx]}" "${NODE_SOCKET_PORTS[$idx]}"
}

log() {
    printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

post_json() {
    local url="$1"
    local payload="$2"
    log "POST ${url} payload=${payload}"
    curl -sS -X POST "${url}" -H "Content-Type: application/json" -d "${payload}"
    echo
}

post_empty() {
    local url="$1"
    log "POST ${url}"
    curl -sS -X POST "${url}"
    echo
}

get_call() {
    local url="$1"
    log "GET ${url}"
    curl -sS "${url}"
    echo
}

sleep_then_log() {
    local seconds="$1"
    log "Sleeping ${seconds}s"
    sleep "${seconds}"
}

log "=== Resetting delays to 0.0 ==="
for idx in 1 2 3 4 5; do
    post_json "${NODE_URLS[$idx]}/setDelay" '{"delay": 0.0}'
done
sleep_then_log 1

log "=== Building ring via node 1 ==="
post_json "${NODE_URLS[1]}/join" "$(join_payload 2)"
sleep_then_log 1
post_json "${NODE_URLS[1]}/join" "$(join_payload 3)"
sleep_then_log 1
post_json "${NODE_URLS[1]}/join" "$(join_payload 4)"
sleep_then_log 1
post_json "${NODE_URLS[1]}/join" "$(join_payload 5)"
sleep_then_log 1

log "=== Baseline election from node 1 ==="
post_empty "${NODE_URLS[1]}/startElection"
sleep_then_log 5

log "=== Setting shared variable via node 1 ==="
post_json "${NODE_URLS[1]}/variable" '{"value": 101}'
get_call "${NODE_URLS[3]}/variable"
sleep_then_log 2

log "=== Enabling 2.5s delay on nodes 1-3 ==="
for idx in 1 2 3; do
    post_json "${NODE_URLS[$idx]}/setDelay" '{"delay": 2.5}'
done
sleep_then_log 1

log "=== Starting simultaneous elections (nodes 1-3) ==="
post_empty "${NODE_URLS[1]}/startElection"
sleep 0.5
post_empty "${NODE_URLS[2]}/startElection"
sleep 0.5
post_empty "${NODE_URLS[3]}/startElection"
sleep_then_log 8

log "=== Resetting delays to 0.0 ==="
for idx in 1 2 3 4 5; do
    post_json "${NODE_URLS[$idx]}/setDelay" '{"delay": 0.0}'
done
sleep_then_log 2

log "=== Killing node 2 and observing election recovery ==="
post_empty "${NODE_URLS[2]}/kill"
sleep_then_log 3
get_call "${NODE_URLS[3]}/variable"
sleep_then_log 5

log "=== Reviving node 2 ==="
post_empty "${NODE_URLS[2]}/revive"
sleep_then_log 3

log "=== Forcing node 3 to leave the ring ==="
post_empty "${NODE_URLS[3]}/leave"
sleep_then_log 3

log "=== Rejoining node 3 via node 1 ==="
post_json "${NODE_URLS[1]}/join" "$(join_payload 3)"
sleep_then_log 2
post_empty "${NODE_URLS[3]}/startElection"
sleep_then_log 5

log "=== Updating shared variable and reading from node 5 ==="
post_json "${NODE_URLS[1]}/variable" '{"value": 202}'
get_call "${NODE_URLS[5]}/variable"
sleep_then_log 2

log "=== Final delay reset ==="
for idx in 1 2 3 4 5; do
    post_json "${NODE_URLS[$idx]}/setDelay" '{"delay": 0.0}'
done
sleep_then_log 1

log "=== Demo complete ==="

#!/bin/bash

set -euo pipefail

NODE1="http://192.168.56.103:8000"
NODE2="http://192.168.56.104:8000"
NODE3="http://192.168.56.105:8000"
NODE4="http://192.168.56.106:8000"
NODE5="http://192.168.56.107:8000"

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
for node in "$NODE1" "$NODE2" "$NODE3" "$NODE4" "$NODE5"; do
    post_json "${node}/setDelay" '{"delay": 0.0}'
done
sleep_then_log 1

log "=== Building ring via node 1 ==="
post_json "${NODE1}/join" '{"node_id": 2, "host": "http://192.168.56.104:8000", "socket_port": 9002}'
sleep_then_log 1
post_json "${NODE1}/join" '{"node_id": 3, "host": "http://192.168.56.105:8000", "socket_port": 9003}'
sleep_then_log 1
post_json "${NODE1}/join" '{"node_id": 4, "host": "http://192.168.56.106:8000", "socket_port": 9004}'
sleep_then_log 1
post_json "${NODE1}/join" '{"node_id": 5, "host": "http://192.168.56.107:8000", "socket_port": 9005}'
sleep_then_log 1

log "=== Baseline election from node 1 ==="
post_empty "${NODE1}/startElection"
sleep_then_log 5

log "=== Setting shared variable via node 1 ==="
post_json "${NODE1}/variable" '{"value": 101}'
get_call "${NODE3}/variable"
sleep_then_log 2

log "=== Enabling 2.5s delay on nodes 1-3 ==="
for node in "$NODE1" "$NODE2" "$NODE3"; do
    post_json "${node}/setDelay" '{"delay": 2.5}'
done
sleep_then_log 1

log "=== Starting simultaneous elections (nodes 1-3) ==="
post_empty "${NODE1}/startElection"
sleep 0.5
post_empty "${NODE2}/startElection"
sleep 0.5
post_empty "${NODE3}/startElection"
sleep_then_log 8

log "=== Resetting delays to 0.0 ==="
for node in "$NODE1" "$NODE2" "$NODE3" "$NODE4" "$NODE5"; do
    post_json "${node}/setDelay" '{"delay": 0.0}'
done
sleep_then_log 2

log "=== Killing node 2 and observing election recovery ==="
post_empty "${NODE2}/kill"
sleep_then_log 3
get_call "${NODE3}/variable"
sleep_then_log 5

log "=== Reviving node 2 ==="
post_empty "${NODE2}/revive"
sleep_then_log 3

log "=== Forcing node 3 to leave the ring ==="
post_empty "${NODE3}/leave"
sleep_then_log 3

log "=== Rejoining node 3 via node 1 ==="
post_json "${NODE1}/join" '{"node_id": 3, "host": "http://192.168.56.105:8000", "socket_port": 9003}'
sleep_then_log 2
post_empty "${NODE3}/startElection"
sleep_then_log 5

log "=== Updating shared variable and reading from node 5 ==="
post_json "${NODE1}/variable" '{"value": 202}'
get_call "${NODE5}/variable"
sleep_then_log 2

log "=== Final delay reset ==="
for node in "$NODE1" "$NODE2" "$NODE3" "$NODE4" "$NODE5"; do
    post_json "${node}/setDelay" '{"delay": 0.0}'
done
sleep_then_log 1

log "=== Demo complete ==="

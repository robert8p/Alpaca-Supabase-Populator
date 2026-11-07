#!/bin/bash
set -Eeuo pipefail
cd "$OUTPUT_DIR"
test "$(id -u)" -ne 0
mkdir -m 700 pgdata socket
initdb -D pgdata -U fixture_bootstrap --auth-local=trust --auth-host=reject --no-locale -E UTF8 > initdb.log
pg_ctl -D pgdata -l postgres.log -o "-k $OUTPUT_DIR/socket -c listen_addresses='' -c max_connections=20" -w start
stop_server() { pg_ctl -D pgdata -m fast -w stop > shutdown.log; }
trap stop_server EXIT
python3 "$INPUT_DIR/smoke.py"

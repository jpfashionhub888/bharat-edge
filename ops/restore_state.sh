#!/usr/bin/env bash
set -euo pipefail
archive=${1:-}
mode=${2:---verify-only}
if [ -z "$archive" ] || [ ! -f "$archive" ]; then
  echo "Usage: $0 ARCHIVE [--verify-only|--restore]" >&2; exit 2
fi
sha256sum -c "$archive.sha256"
if tar -tzf "$archive" | grep -Ev '^(logs|models)/[^/]+$' | grep -q .; then
  echo 'Unsafe archive path' >&2; exit 3
fi
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
tar -xzf "$archive" -C "$tmp"
python3 - "$tmp" <<'PY'
import json, pathlib, sys
for path in pathlib.Path(sys.argv[1]).rglob('*.json'):
    json.loads(path.read_text(encoding='utf-8'))
print('RESTORE_VERIFY_OK')
PY
if [ "$mode" = "--verify-only" ]; then exit 0; fi
if [ "$mode" != "--restore" ]; then echo 'Unknown mode' >&2; exit 2; fi
systemctl stop bharatedge-scan.service bharatedge-dashboard.service
cp -a "$tmp/logs/." /opt/bharatedge/logs/ 2>/dev/null || true
cp -a "$tmp/models/." /opt/bharatedge/models/ 2>/dev/null || true
chown -R ubuntu:ubuntu /opt/bharatedge/logs /opt/bharatedge/models
systemctl start bharatedge-dashboard.service
curl -fsS http://127.0.0.1:8050/healthz >/dev/null
echo RESTORE_OK

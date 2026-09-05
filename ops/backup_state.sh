#!/usr/bin/env bash
set -euo pipefail
root=/opt/bharatedge
dest=/var/backups/bharatedge
stamp=$(date -u +%Y%m%dT%H%M%SZ)
archive="$dest/state-$stamp.tar.gz"
install -d -m 700 "$dest"
cd "$root"
mapfile -t files < <(find logs models -maxdepth 1 -type f \
  \( -name '*.json' -o -name '*.json.bak' -o -name '*.jsonl' -o -name '*.pkl' \) -print 2>/dev/null | sort)
if [ "${#files[@]}" -eq 0 ]; then echo "No state files found" >&2; exit 1; fi
tar -czf "$archive" "${files[@]}"
chmod 600 "$archive"
sha256sum "$archive" > "$archive.sha256"
chmod 600 "$archive.sha256"
tar -tzf "$archive" >/dev/null
find "$dest" -type f -name 'state-*' -mtime +30 -delete
echo "BACKUP_OK $archive"

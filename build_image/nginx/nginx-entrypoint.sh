#!/bin/sh
set -eu

case "${HOSTNAME:-}" in
  ''|*[!A-Za-z0-9_.-]*) echo 'Invalid nginx instance ID' >&2; exit 2 ;;
esac
case "${NGINX_LOG_MAX_BYTES:-10485760}" in *[!0-9]*|'') echo 'Invalid nginx log size' >&2; exit 2;; esac
case "${NGINX_LOG_BACKUP_COUNT:-5}" in *[!0-9]*|'') echo 'Invalid nginx backup count' >&2; exit 2;; esac
MAX_BYTES=${NGINX_LOG_MAX_BYTES:-10485760}
BACKUPS=${NGINX_LOG_BACKUP_COUNT:-5}
[ "$MAX_BYTES" -ge 1024 ] || { echo 'Nginx log size must be at least 1024' >&2; exit 2; }
[ "$BACKUPS" -ge 1 ] && [ "$BACKUPS" -le 20 ] || { echo 'Nginx backup count must be 1-20' >&2; exit 2; }

LOG_BASE=${LOG_ROOT:-/log}
[ ! -L "$LOG_BASE" ] || { echo 'Nginx log root cannot be a symlink' >&2; exit 2; }
mkdir -p "$LOG_BASE"
# Nginx workers reopen logs after rotation as uid nginx. The shared deployment
# log root may be created as 0700 by another root process; grant traverse only,
# without directory listing, so the worker can reach its owned activity file.
chmod 0711 "$LOG_BASE"
LOG_DIR=$LOG_BASE/nginx/$HOSTNAME
[ ! -L "$LOG_DIR" ] || { echo 'Nginx log directory cannot be a symlink' >&2; exit 2; }
mkdir -p "$LOG_DIR"
for path in "$LOG_DIR"/events.jsonl "$LOG_DIR"/events.jsonl.*; do
  [ ! -L "$path" ] || { echo 'Nginx log file cannot be a symlink' >&2; exit 2; }
done
target=$LOG_DIR/events.jsonl
create_log_file() {
  [ ! -e "$target" ] || { echo 'Refusing to replace nginx log file' >&2; exit 2; }
  : > "$target"
  chown nginx:nginx "$target"
  chmod 0644 "$target"
}
[ -e "$target" ] || create_log_file

sed "s/__NGINX_INSTANCE__/$HOSTNAME/g" /etc/nginx/nginx.conf > /tmp/nginx.conf
nginx -t -c /tmp/nginx.conf
nginx -c /tmp/nginx.conf -g 'daemon off;' &
NGINX_PID=$!

terminate() { kill -TERM "$NGINX_PID" 2>/dev/null || true; }
graceful_stop() { kill -QUIT "$NGINX_PID" 2>/dev/null || true; }
reload() { kill -HUP "$NGINX_PID" 2>/dev/null || true; }
trap terminate TERM INT
trap graceful_stop QUIT
trap reload HUP

while kill -0 "$NGINX_PID" 2>/dev/null; do
  # BusyBox ash may defer traps while waiting for the sleep child. Keep the
  # polling interval short so Docker's SIGQUIT reaches nginx promptly.
  sleep 1 & wait $! || true
  [ -f "$target" ] || continue
  size=$(stat -c %s "$target" 2>/dev/null || echo 0)
  [ "$size" -ge "$MAX_BYTES" ] || continue
  index=$BACKUPS
  while [ "$index" -gt 1 ]; do
    previous=$((index - 1))
    [ ! -f "$target.$previous" ] || mv -f "$target.$previous" "$target.$index"
    index=$previous
  done
  mv -f "$target" "$target.1"
  create_log_file
  nginx -c /tmp/nginx.conf -s reopen
done
wait "$NGINX_PID"

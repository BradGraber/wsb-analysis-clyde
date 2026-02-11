#!/bin/bash
# manage-logs.sh — Enable, disable, clear, or check status of implementation phase logging.
# Usage: manage-logs.sh [on|off|clear|status]
# No argument defaults to "status".

set -e

LOG_DIR="output/logs"
FLAG_FILE="$LOG_DIR/.enabled"

cmd="${1:-status}"

case "$cmd" in
  on)
    mkdir -p "$LOG_DIR"
    touch "$FLAG_FILE"
    echo "Logging enabled. Subagent transcripts and orchestrator tool calls will be written to $LOG_DIR/"
    ;;

  off)
    rm -f "$FLAG_FILE"
    echo "Logging disabled. Existing logs preserved — run '$0 clear' to remove them."
    ;;

  clear)
    if [ ! -d "$LOG_DIR" ] || [ -z "$(find "$LOG_DIR" -maxdepth 1 -type f ! -name .enabled 2>/dev/null)" ]; then
      echo "No logs to clear."
    else
      count=$(find "$LOG_DIR" -maxdepth 1 -type f ! -name .enabled | wc -l)
      size=$(find "$LOG_DIR" -maxdepth 1 -type f ! -name .enabled -exec du -cb {} + 2>/dev/null | tail -1 | cut -f1)
      size_kb=$(( (size + 1023) / 1024 ))
      find "$LOG_DIR" -maxdepth 1 -type f ! -name .enabled -delete
      enabled="OFF"
      [ -f "$FLAG_FILE" ] && enabled="ON"
      echo "Cleared $count log files (${size_kb} KB). Logging is $enabled."
    fi
    ;;

  status)
    if [ -f "$FLAG_FILE" ]; then
      echo "Logging: ON"
      if [ -d "$LOG_DIR" ]; then
        count=$(find "$LOG_DIR" -maxdepth 1 -type f ! -name .enabled | wc -l)
        if [ "$count" -gt 0 ]; then
          size=$(find "$LOG_DIR" -maxdepth 1 -type f ! -name .enabled -exec du -cb {} + 2>/dev/null | tail -1 | cut -f1)
          size_kb=$(( (size + 1023) / 1024 ))
          echo "Log files: $count (${size_kb} KB) in $LOG_DIR/"
        else
          echo "No log files yet."
        fi
      fi
    else
      echo "Logging: OFF"
    fi
    ;;

  *)
    echo "Usage: $0 [on|off|clear|status]" >&2
    exit 1
    ;;
esac

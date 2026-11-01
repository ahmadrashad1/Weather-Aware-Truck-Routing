#!/usr/bin/env bash
# Emails through Resend when a Lightsail alarm starts or stops firing, because Lightsail alarms can
# only notify through AWS's own contact methods. Usage: check-alarms.sh <state-file>
set -euo pipefail

: "${INSTANCE:?Set INSTANCE}"
state_file="$1"
here="$(cd "$(dirname "$0")" && pwd)"

current="$(aws lightsail get-alarms --monitored-resource-name "$INSTANCE" \
  --query 'alarms[].[name,state]' --output text | sort)"
previous="$(cat "$state_file" 2>/dev/null || true)"

firing_in() { awk -F'\t' '$2 == "ALARM" {print $1}' <<<"$1"; }
now_firing="$(firing_in "$current")"
was_firing="$(firing_in "$previous")"
started="$(comm -13 <(sort <<<"$was_firing") <(sort <<<"$now_firing") | sed '/^$/d' | paste -sd, -)"
stopped="$(comm -23 <(sort <<<"$was_firing") <(sort <<<"$now_firing") | sed '/^$/d' | paste -sd, -)"

# The state is only saved once the emails have gone, so a failed send is tried again next run.
if [ -n "$started" ]; then
  bash "$here/send-alert.sh" "Server alarm: $started" \
    "These alarms are firing: $started. Current states: $current"
fi
if [ -n "$stopped" ]; then
  bash "$here/send-alert.sh" "Server recovered: $stopped" \
    "These alarms have stopped firing: $stopped. Current states: $current"
fi
printf '%s\n' "$current" >"$state_file"

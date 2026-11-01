#!/usr/bin/env bash
# Emails an alert through Resend. Usage: send-alert.sh <subject> <text>
# The free sender only delivers to your own Resend account's address. See docs/deployment.md.
set -euo pipefail

: "${RESEND_API_KEY:?Set RESEND_API_KEY}" "${ALERT_EMAIL:?Set ALERT_EMAIL}"
from="${ALERT_FROM:-Truck Routing Alerts <onboarding@resend.dev>}"

# The key goes through curl's config, so it never appears in a process list.
jq -n --arg from "$from" --arg to "$ALERT_EMAIL" --arg subject "$1" --arg text "$2" \
  '{from: $from, to: [$to], subject: $subject, text: $text}' |
  curl -fsS --max-time 20 -o /dev/null -X POST https://api.resend.com/emails \
    -K <(printf 'header = "Authorization: Bearer %s"\n' "$RESEND_API_KEY") \
    -H 'Content-Type: application/json' --data-binary @-

#!/usr/bin/env bash
# Creates or updates the server's Lightsail alarms. Safe to run again.
# Alarms email you once a contact method is confirmed. See docs/deployment.md.
set -euo pipefail

INSTANCE=truck-routing
contact=()
if [ "$(aws lightsail get-contact-methods --query "length(contactMethods[?status=='Valid'])" --output text)" != 0 ]; then
  contact=(--contact-protocols Email)
fi

put_alarm() {
  local name="$1" metric="$2" operator="$3" threshold="$4" periods="$5"
  aws lightsail put-alarm --alarm-name "$INSTANCE-$name" --metric-name "$metric" \
    --monitored-resource-name "$INSTANCE" --comparison-operator "$operator" \
    --threshold "$threshold" --evaluation-periods "$periods" --datapoints-to-alarm "$periods" \
    --treat-missing-data notBreaching --notification-triggers ALARM OK "${contact[@]}" >/dev/null
  echo "Set $INSTANCE-$name"
}

# Each period is 5 minutes.
put_alarm high-cpu CPUUtilization GreaterThanOrEqualToThreshold 80 3
put_alarm low-burst BurstCapacityPercentage LessThanOrEqualToThreshold 5 3
put_alarm status-check StatusCheckFailed GreaterThanOrEqualToThreshold 1 2

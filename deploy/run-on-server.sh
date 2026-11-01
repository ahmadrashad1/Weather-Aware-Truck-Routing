#!/usr/bin/env bash
# Runs a command on the server from a GitHub Actions job that's signed in to AWS through OIDC.
# Port 22 must already be open to the runner. The command's exit code becomes this script's.
set -euo pipefail

: "${INSTANCE:?Set INSTANCE}" "${SERVER_KNOWN_HOSTS:?Set SERVER_KNOWN_HOSTS}"

keys="$(mktemp -d)"
trap 'rm -rf "$keys"' EXIT

# Lightsail issues an SSH key and certificate that expire within minutes.
aws lightsail get-instance-access-details --instance-name "$INSTANCE" --protocol ssh >"$keys/access.json"
jq -r .accessDetails.privateKey "$keys/access.json" >"$keys/key"
jq -r .accessDetails.certKey "$keys/access.json" >"$keys/key-cert.pub"
user="$(jq -r .accessDetails.username "$keys/access.json")"
address="$(jq -r .accessDetails.ipAddress "$keys/access.json")"
rm "$keys/access.json"
chmod 600 "$keys/key"
printf '%s\n' "$SERVER_KNOWN_HOSTS" >"$keys/known_hosts"

ssh_to_server() {
  ssh -i "$keys/key" -o CertificateFile="$keys/key-cert.pub" \
    -o UserKnownHostsFile="$keys/known_hosts" -o StrictHostKeyChecking=yes \
    -o BatchMode=yes -o ConnectTimeout=10 "$user@$address" "$@"
}

# The firewall change can take a moment to apply.
for attempt in $(seq 1 12); do
  ssh_to_server true && break
  if [ "$attempt" = 12 ]; then
    echo "::error::Couldn't connect to the server"
    exit 1
  fi
  sleep 5
done

ssh_to_server "$@"

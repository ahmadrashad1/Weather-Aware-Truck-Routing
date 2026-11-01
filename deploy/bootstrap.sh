#!/bin/sh
# Prepares a new Ubuntu 24.04 Lightsail server. Passed as its launch script, so it runs once as root.
# The API keys are added separately, and updates start once they exist. See docs/deployment.md.
#
# This must stay plain POSIX sh. Lightsail puts its own `#!/bin/sh` setup in front of a launch
# script, so its shebang is ignored, and bash features such as `set -o pipefail` stop it at boot.
set -eu

ROOT=/opt/truck-routing
REPO_URL=https://github.com/ahmadrashad1/Weather-Aware-Truck-Routing.git

# Swap gives a 1 GB server room to absorb a spike rather than killing a container.
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >>/etc/fstab
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y docker.io docker-compose-v2 git

# Stops container logs from slowly filling the disk.
mkdir -p /etc/docker
cat >/etc/docker/daemon.json <<'JSON'
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" } }
JSON
systemctl enable --now docker
systemctl restart docker

mkdir -p "$ROOT/state"
chmod 700 "$ROOT"
[ -d "$ROOT/repo" ] || git clone --quiet "$REPO_URL" "$ROOT/repo"

cp "$ROOT/repo/deploy/truck-routing-update.service" /etc/systemd/system/
cp "$ROOT/repo/deploy/truck-routing-update.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now truck-routing-update.timer

#!/usr/bin/env bash
# Started on the server by the Deploy workflow. It deploys whatever revision GitHub has published
# as `production`, and rolls back if that revision doesn't come up healthy.
set -euo pipefail

ROOT="${TRUCK_ROOT:-/opt/truck-routing}"
REPO="$ROOT/repo"
STATE="$ROOT/state"
IMAGES="ghcr.io/ahmadrashad1/weather-aware-truck-routing"
WAIT_SECONDS=180

compose() {
  local tag="$1"
  shift
  IMAGE_TAG="$tag" docker compose \
    --project-name truck-routing \
    --project-directory "$REPO" \
    --env-file "$ROOT/.env" \
    -f "$REPO/docker-compose.yml" \
    -f "$REPO/deploy/docker-compose.prod.yml" \
    "$@"
}

read_state() {
  cat "$STATE/$1" 2>/dev/null || true
}

published_revision() {
  docker pull --quiet "$IMAGES/backend:production" >/dev/null
  docker image inspect \
    --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
    "$IMAGES/backend:production"
}

deploy() {
  local revision="$1"
  # The Compose files come from the same revision as the images, so they can't disagree.
  git -C "$REPO" fetch --quiet origin
  git -C "$REPO" checkout --detach "$revision"
  compose "$revision" pull --quiet &&
    compose "$revision" up --detach --no-build --remove-orphans --wait \
      --wait-timeout "$WAIT_SECONDS" &&
    compose "$revision" exec -T frontend wget -qO- http://127.0.0.1:8080/api/v1/health |
    grep -q "\"version\": \"$revision\""
}

main() {
  local target current
  target="$(published_revision)"
  current="$(read_state current)"

  if [ -z "$target" ]; then
    echo "The published image has no revision label, so it won't be deployed." >&2
    return 1
  fi
  if [ "$target" = "$current" ] || [ "$target" = "$(read_state failed)" ]; then
    return 0
  fi

  echo "Deploying $target"
  if deploy "$target"; then
    echo "$target" >"$STATE/current"
    rm -f "$STATE/failed"
    docker image prune --all --force --filter "until=72h" >/dev/null
    echo "Deployed $target"
    return 0
  fi

  # Remembered so a bad revision isn't retried on every run, until a new one is published.
  echo "$target" >"$STATE/failed"
  echo "Deploying $target failed" >&2
  if [ -n "$current" ]; then
    echo "Rolling back to $current" >&2
    deploy "$current" || echo "Rolling back to $current failed too" >&2
  fi
  return 1
}

# Everything is in functions, because a checkout can replace this file while it runs.
main "$@"
exit $?

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT="${1:-$ROOT_DIR/dist/race-timing-release.tar.gz}"
DEPLOY_HOST="${DEPLOY_HOST:-}"
DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/race-timing}"
DEPLOY_PORT="${DEPLOY_PORT:-22}"

if [ -z "$DEPLOY_HOST" ]; then
  echo "DEPLOY_HOST is required" >&2
  exit 1
fi

if [ ! -f "$ARTIFACT" ]; then
  echo "Artifact not found: $ARTIFACT" >&2
  exit 1
fi

ARCHIVE_NAME="$(basename "$ARTIFACT")"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -p "$DEPLOY_PORT")

scp "${SSH_OPTS[@]}" "$ARTIFACT" "$DEPLOY_USER@$DEPLOY_HOST:/tmp/$ARCHIVE_NAME"
scp "${SSH_OPTS[@]}" "$ROOT_DIR/deploy/race-timing.service" "$DEPLOY_USER@$DEPLOY_HOST:/tmp/race-timing.service"
scp "${SSH_OPTS[@]}" "$ROOT_DIR/deploy/nginx/race-timing.conf" "$DEPLOY_USER@$DEPLOY_HOST:/tmp/race-timing.conf"

ssh "${SSH_OPTS[@]}" "$DEPLOY_USER@$DEPLOY_HOST" "bash -s" <<REMOTE
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

if [ "$(id -u)" -eq 0 ]; then
  apt-get update
  apt-get install -y python3 python3-venv python3-pip nginx
else
  sudo apt-get update
  sudo apt-get install -y python3 python3-venv python3-pip nginx
fi

mkdir -p '$DEPLOY_PATH/current' '$DEPLOY_PATH/shared/instance' '$DEPLOY_PATH/shared/uploads'
rm -rf '$DEPLOY_PATH/current'/* '$DEPLOY_PATH/current'/.[!.]* '$DEPLOY_PATH/current'/..?* 2>/dev/null || true
tar -xzf /tmp/$ARCHIVE_NAME -C '$DEPLOY_PATH/current'
rm -f /tmp/$ARCHIVE_NAME

python3 -m venv '$DEPLOY_PATH/current/.venv'
'$DEPLOY_PATH/current/.venv/bin/pip' install --upgrade pip
'$DEPLOY_PATH/current/.venv/bin/pip' install -r '$DEPLOY_PATH/current/requirements.txt'

ln -sfn '$DEPLOY_PATH/shared/instance' '$DEPLOY_PATH/current/instance'
ln -sfn '$DEPLOY_PATH/shared/uploads' '$DEPLOY_PATH/current/uploads'

install -m 0644 /tmp/race-timing.service /etc/systemd/system/race-timing.service
install -m 0644 /tmp/race-timing.conf /etc/nginx/sites-available/race-timing.conf
ln -sfn /etc/nginx/sites-available/race-timing.conf /etc/nginx/sites-enabled/race-timing.conf
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
systemctl enable race-timing || true
systemctl restart race-timing
nginx -t
systemctl reload nginx || true
REMOTE

echo "Deployment completed successfully."

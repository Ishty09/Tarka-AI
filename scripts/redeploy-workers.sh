#!/bin/bash
# Manual workers redeploy — run this on the droplet when Coolify can't.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Ishty09/Tarka-AI/main/scripts/redeploy-workers.sh | bash
#
# What it does:
#   1. Clones latest main from GitHub.
#   2. Builds a new quarrel-workers:latest image.
#   3. Captures the running workers container's env, network, and port
#      bindings (so we don't lose secrets or routing).
#   4. Stops + removes the old container.
#   5. Starts a new one from the freshly built image, with the same
#      env / network / ports.
#   6. Waits ~8s, hits /health, and reports whether the build_marker is
#      now visible (confirms latest code is running).
#
# Why this exists: the GitHub→Coolify webhook for workers either was
# never configured or has broken. Until that's fixed, this script is
# the manual deploy path. CLAUDE.md §27 step 47/48 will replace it.

set -euo pipefail

BUILD_DIR="/root/tarka-build"
REPO="https://github.com/Ishty09/Tarka-AI.git"

log() { printf "==> %s\n" "$*"; }

log "Step 1/6 — Pulling latest code"
rm -rf "$BUILD_DIR"
git clone --depth 1 "$REPO" "$BUILD_DIR" > /dev/null 2>&1
cd "$BUILD_DIR"
COMMIT_SHORT=$(git rev-parse --short HEAD)
log "    Commit on main: $COMMIT_SHORT"

log "Step 2/6 — Building workers image (takes 1-3 min)"
# Build context must be apps/workers/ — the Dockerfile's COPY commands
# reference pyproject.toml and ./app relative to that directory, not
# the repo root.
if ! docker build -t quarrel-workers:latest apps/workers > /tmp/workers-build.log 2>&1; then
  log "    BUILD FAILED. Last 30 lines:"
  tail -30 /tmp/workers-build.log
  exit 1
fi
log "    Image built: quarrel-workers:latest"

log "Step 3/6 — Capturing old container config"
if ! docker inspect workers > /tmp/workers-old.json 2>/dev/null; then
  log "    No existing 'workers' container found. Cannot infer env/network."
  log "    Set them up manually or via Coolify, then re-run this script."
  exit 1
fi
NETWORK=$(docker inspect workers --format '{{range $k,$v:=.NetworkSettings.Networks}}{{$k}}{{end}}' | head -1)
log "    Network: $NETWORK"
docker inspect workers --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -v '^$' > /tmp/workers.env
ENV_COUNT=$(wc -l < /tmp/workers.env)
log "    Env vars carried over: $ENV_COUNT"
PORT_FLAGS=$(docker inspect workers --format '{{json .HostConfig.PortBindings}}' \
  | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin) or {}
except Exception:
    d = {}
out = []
for k, v in d.items():
    cp = k.split('/')[0]
    for b in v or []:
        hp = b.get('HostPort','').strip()
        hi = b.get('HostIp','').strip()
        if hp:
            out.append(f'-p {hi+\":\" if hi else \"\"}{hp}:{cp}')
print(' '.join(out))
")
log "    Port bindings: ${PORT_FLAGS:-(none)}"

log "Step 4/6 — Stopping old workers container"
docker stop workers > /dev/null
docker rm workers > /dev/null
log "    Stopped + removed"

log "Step 5/6 — Starting new workers container"
# shellcheck disable=SC2086  # PORT_FLAGS intentionally split
docker run -d \
  --name workers \
  --network "$NETWORK" \
  $PORT_FLAGS \
  --env-file /tmp/workers.env \
  --restart unless-stopped \
  quarrel-workers:latest > /dev/null
log "    Started"

log "Step 6/6 — Verifying /health build_marker"
sleep 8
HEALTH=$(docker exec workers python3 -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())" 2>&1 || true)
echo "    /health response: $HEALTH"

if echo "$HEALTH" | grep -q 'build_marker'; then
  echo ""
  echo "✅ SUCCESS — workers now running commit $COMMIT_SHORT"
  echo "   Open https://tarka-ai-alpha.vercel.app/diagnostics to confirm."
else
  echo ""
  echo "⚠️  Container is up but /health did not return build_marker."
  echo "   That could mean: latest commit doesn't include the marker change yet,"
  echo "   or the workers process hasn't finished starting."
  echo "   Tail the logs:  docker logs workers --tail 30"
fi

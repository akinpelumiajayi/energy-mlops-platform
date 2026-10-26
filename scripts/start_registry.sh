#!/usr/bin/env bash
# Start a local container registry on localhost:5001 for the kind cluster to pull from.
# This is the pattern documented by the kind project: https://kind.sigs.k8s.io/docs/user/local-registry/
set -euo pipefail
NAME="${1:-kind-registry}"
if [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null || true)" != "true" ]; then
  docker run -d --restart=always -p 127.0.0.1:5001:5000 --network bridge --name "$NAME" registry:2
fi
echo "registry $NAME running on localhost:5001"

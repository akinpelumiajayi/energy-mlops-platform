#!/usr/bin/env bash
# Copy a locally built Docker image into every node of a kind cluster.
# Usage: scripts/load_image_into_kind.sh <image> <cluster-name>
#
# Tries `kind load docker-image` first. Newer Docker versions (29+) use the containerd
# image store, which older kind releases fail on with "failed to detect containerd
# snapshotter". The fallback streams the image into each node's containerd with ctr.
set -euo pipefail

IMAGE="$1"
CLUSTER="$2"

if kind load docker-image "$IMAGE" --name "$CLUSTER"; then
  exit 0
fi

echo "kind load failed, importing with ctr instead"
for node in $(kind get nodes --name "$CLUSTER"); do
  echo "-> $node"
  { docker save --platform linux/amd64 "$IMAGE" 2>/dev/null || docker save "$IMAGE"; } \
    | docker exec -i "$node" ctr --namespace=k8s.io images import --all-platforms --digests -
done
for node in $(kind get nodes --name "$CLUSTER"); do
  docker exec "$node" crictl images | grep -q "${IMAGE%%:*}" || { echo "image missing on $node"; exit 1; }
done
echo "image $IMAGE loaded on all nodes"

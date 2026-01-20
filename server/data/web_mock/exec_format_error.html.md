# Result: "exec /bin/bash: exec format error" in Kubernetes

This usually indicates image architecture mismatch:
- Running linux/arm64 image on linux/amd64 node (or vice versa)

Verification:
- skopeo inspect docker://IMAGE | jq '.Architecture, .Os'
- docker manifest inspect IMAGE

Fix:
- Use an amd64 image tag, or build multi-arch image (docker buildx)

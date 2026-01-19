# Kubernetes: exec format error (image architecture mismatch)

## Symptoms
- Pod in CrashLoopBackOff
- Logs/events show: "exec /bin/bash: exec format error"
- Container starts then exits immediately

## Root cause
The container image was built for a different CPU architecture (e.g., linux/arm64) than the node (e.g., linux/amd64).

## Verify
- Check node architecture:
  - uname -m
- Check image manifest platforms:
  - docker manifest inspect <image>
  - skopeo inspect docker://<image>

## Fix
- Use an amd64 image tag or rebuild image for amd64.
- Ensure multi-arch build (buildx) if needed.

## Common commands
kubectl describe pod <pod> -n <ns>
kubectl get node -o wide
kubectl logs <pod> -n <ns> --previous

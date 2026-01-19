# Kubernetes: ImagePullBackOff / ErrImagePull

## Symptoms
- Pod Pending / ImagePullBackOff
- Events: "Failed to pull image", "no match for platform", "401 Unauthorized", "not found"

## Root causes
- Wrong image tag / image not present
- Registry auth/secret missing
- Network/DNS/proxy issues
- Platform mismatch

## Verify
kubectl describe pod <pod> -n <ns>
kubectl get secret -n <ns>
kubectl get events -n <ns> --sort-by=.metadata.creationTimestamp

## Fix
- Correct image tag
- Add imagePullSecrets to service account or pod spec
- Verify registry credentials

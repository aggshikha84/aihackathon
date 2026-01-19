# Kubernetes: OOMKilled

## Symptoms
- Pod restarts; describe shows "OOMKilled"
- Exit code 137

## Root cause
Container exceeded memory limit.

## Verify
kubectl describe pod <pod> -n <ns>
kubectl top pod <pod> -n <ns>   (if metrics-server present)

## Fix
- Increase memory requests/limits
- Reduce workload memory usage
- Check leaks / batch sizes

# Kubernetes: CrashLoopBackOff quick triage

## Symptoms
- Pod restarts repeatedly
- Status: CrashLoopBackOff

## Triage steps
1) kubectl describe pod <pod> -n <ns>
2) kubectl logs <pod> -n <ns> --previous
3) Check config/env, missing secrets, command args
4) Check resources: OOMKilled

## Common causes
- Application exit on startup
- Bad config
- Missing secret/configmap
- Image architecture mismatch
- OOMKilled

## Safe actions
- Increase log verbosity
- Roll back to previous image tag
- Check readiness/liveness probes

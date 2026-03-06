# Kubernetes Diagnostic Patterns

## Pod CrashLoopBackOff

**Symptoms:** Pod restarts repeatedly, status shows `CrashLoopBackOff`.

**Diagnostic steps:**
1. Check pod logs: `kubectl logs <pod> --previous` (shows logs from crashed container)
2. Check pod events: `kubectl describe pod <pod>` (look at Events section)
3. Check resource limits: OOMKilled appears when memory limit is exceeded
4. Check entrypoint: Ensure the container command exists and is executable

**Flox-specific causes:**
- Image built with `flox containerize` missing a runtime dependency
- Hook script in the container failing on startup
- Service command in manifest.toml has a typo or missing binary

**Resolution pattern:**
```bash
# Get crash reason
kubectl describe pod <pod> | grep -A5 "Last State"

# If OOMKilled, increase memory limit
# If Error, check the entrypoint command exists in the container
kubectl exec -it <pod> -- /bin/sh -c "which <command>"
```

## ImagePullBackOff

**Symptoms:** Pod stuck in `ImagePullBackOff` or `ErrImagePull`.

**Diagnostic steps:**
1. Check image name and tag: `kubectl describe pod <pod> | grep Image`
2. Check pull policy: `imagePullPolicy: Never` required for Kind-loaded images
3. Check registry auth: `kubectl get secret` for image pull secrets
4. For Kind: Verify image was loaded with `docker images | grep <image>`

**Flox-specific causes:**
- Forgot to run `kind load docker-image` after `flox containerize | docker load`
- Image tag mismatch between manifest and Kind-loaded image
- `imagePullPolicy` not set to `Never` for local images

**Resolution pattern:**
```bash
# Load image into Kind cluster
kind load docker-image myapp:dev --name floxdev

# Verify it's available
docker exec -it floxdev-control-plane crictl images | grep myapp

# Ensure manifest has: imagePullPolicy: Never
```

## Kubeconfig Not Found

**Symptoms:** `error: no configuration has been provided` or `unable to connect to server`.

**Diagnostic steps:**
1. Check `KUBECONFIG` env var: `echo $KUBECONFIG`
2. Verify file exists: `ls -la $KUBECONFIG`
3. Check Kind cluster is running: `kind get clusters`
4. Check Docker is running (Kind needs it): `docker info`

**Flox-specific causes:**
- `KUBECONFIG` set to `$FLOX_ENV_CACHE/kubeconfig` but file not yet created
- Kind cluster was deleted but kubeconfig still references it
- Docker daemon stopped, so Kind cluster is unreachable

**Resolution pattern:**
```bash
# Recreate kubeconfig from existing Kind cluster
kind export kubeconfig --name floxdev --kubeconfig "$KUBECONFIG"

# Or recreate the cluster
kind delete cluster --name floxdev
kind create cluster --name floxdev --kubeconfig "$KUBECONFIG"
```

## Helm Release Failures

**Symptoms:** `helm install` or `helm upgrade` fails with various errors.

**Common errors and fixes:**

### "cannot re-use a name that is still in use"
```bash
helm list -A  # Check if release exists
helm uninstall <release> -n <namespace>  # Remove it
```

### "rendered manifests contain a resource that already exists"
```bash
# Resource exists but isn't managed by Helm
kubectl annotate <resource> meta.helm.sh/release-name=<release> --overwrite
kubectl annotate <resource> meta.helm.sh/release-namespace=<namespace> --overwrite
kubectl label <resource> app.kubernetes.io/managed-by=Helm --overwrite
```

### "INSTALLATION FAILED: Kubernetes cluster unreachable"
```bash
# Check kubeconfig
kubectl cluster-info
# Re-export from Kind if needed
kind export kubeconfig --name floxdev --kubeconfig "$KUBECONFIG"
```

**Flox-specific causes:**
- Helm cache directories not set up (check `HELM_CACHE_HOME`, `HELM_CONFIG_HOME`, `HELM_DATA_HOME`)
- Helm repos not added in hook (check `helm repo list`)
- Kubeconfig path mismatch between Flox vars and Helm's expectations

## Namespace Stuck in Terminating

**Symptoms:** `kubectl get ns` shows namespace in `Terminating` state indefinitely.

**Resolution:**
```bash
# Remove finalizers to force deletion
kubectl get ns <namespace> -o json | \
  jq '.spec.finalizers = []' | \
  kubectl replace --raw "/api/v1/namespaces/<namespace>/finalize" -f -
```

## General Debugging Checklist

1. Is the cluster reachable? `kubectl cluster-info`
2. Is the namespace correct? `kubectl config get-contexts`
3. Are CRDs up to date? `kubectl get crd`
4. Are RBAC permissions sufficient? Check for `Forbidden` in `kubectl describe pod`
5. Is the Flox kubeconfig pointing to the right cluster? `cat "$KUBECONFIG"`

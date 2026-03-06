# Kubernetes with Flox

Flox provides reproducible Kubernetes tooling without version drift across machines. This guide covers how to manage clusters, Helm charts, and deployments inside a Flox environment.

## Manifest Setup

```toml
[install]
kubectl.pkg-path = "kubectl"
kubectl.version = "^1.30"
helm.pkg-path = "kubernetes-helm"
kustomize.pkg-path = "kustomize"
kind.pkg-path = "kind"
k9s.pkg-path = "k9s"

[vars]
KUBECONFIG = "${FLOX_ENV_CACHE}/kubeconfig"

[hook]
on-activate = """
  # Create kubeconfig location if missing
  mkdir -p "$(dirname "$KUBECONFIG")"

  # Auto-create a Kind cluster for local dev if none exists
  if ! kind get clusters 2>/dev/null | grep -q floxdev; then
    echo "Creating Kind cluster 'floxdev'..."
    kind create cluster --name floxdev --kubeconfig "$KUBECONFIG"
  fi

  # Ensure kubeconfig points to the right cluster
  if [ -f "$KUBECONFIG" ]; then
    kubectl config use-context kind-floxdev 2>/dev/null || true
  fi
"""
```

## Kind Cluster Management

Kind clusters run inside Docker. Flox manages both the Kind binary and the kubeconfig lifecycle. Store kubeconfig in `$FLOX_ENV_CACHE` so it persists across activations but stays project-scoped.

### Loading Local Images

When developing containers locally, load them into Kind instead of pushing to a registry:

```bash
# Build with docker/podman, then load into Kind
docker build -t myapp:dev .
kind load docker-image myapp:dev --name floxdev
```

Set `imagePullPolicy: Never` in your manifests to use locally loaded images.

### Multi-Cluster Setups

For projects needing multiple clusters (e.g., staging + prod simulation):

```toml
[hook]
on-activate = """
  for cluster in staging prod; do
    if ! kind get clusters 2>/dev/null | grep -q "flox-$cluster"; then
      kind create cluster --name "flox-$cluster" \
        --kubeconfig "$FLOX_ENV_CACHE/kubeconfig-$cluster"
    fi
  done
  export KUBECONFIG="$FLOX_ENV_CACHE/kubeconfig-staging"
"""
```

## Helm Chart Development

Keep Helm in the Flox manifest so chart development uses a pinned version across the team:

```toml
[hook]
on-activate = """
  # Cache Helm repos locally
  export HELM_CACHE_HOME="$FLOX_ENV_CACHE/helm/cache"
  export HELM_CONFIG_HOME="$FLOX_ENV_CACHE/helm/config"
  export HELM_DATA_HOME="$FLOX_ENV_CACHE/helm/data"
  mkdir -p "$HELM_CACHE_HOME" "$HELM_CONFIG_HOME" "$HELM_DATA_HOME"

  # Add common repos idempotently
  if ! helm repo list 2>/dev/null | grep -q bitnami; then
    helm repo add bitnami https://charts.bitnami.com/bitnami
    helm repo update
  fi
"""
```

## Namespace Management

Use hooks to ensure namespaces exist before deployments:

```toml
[hook]
on-activate = """
  for ns in dev staging monitoring; do
    kubectl get ns "$ns" 2>/dev/null || kubectl create ns "$ns"
  done
  kubectl config set-context --current --namespace=dev
"""
```

## Deploying with Kustomize

Kustomize overlays work well with Flox environment variables for per-environment configuration:

```bash
# Deploy using kustomize with Flox-managed tools
kubectl apply -k overlays/dev/
```

## Services Integration

Run port-forwards or watchers as Flox services:

```toml
[services]
k9s.command = "k9s --kubeconfig $FLOX_ENV_CACHE/kubeconfig"
port-forward.command = "kubectl port-forward svc/myapp 8080:80"
```

## Key Principles

- Store all cluster state (`KUBECONFIG`, Helm cache) in `$FLOX_ENV_CACHE`
- Guard cluster creation in hooks with existence checks (idempotent)
- Pin kubectl version to match your target cluster version
- Use `kind load docker-image` instead of pushing to registries for local dev
- Never hardcode paths -- use `$FLOX_ENV_CACHE` and `$FLOX_ENV_PROJECT`

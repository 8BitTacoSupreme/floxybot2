# Google Cloud Platform with Flox

Flox manages the Google Cloud SDK, authentication flows, and project switching through manifest hooks, keeping GCP configuration scoped to each project.

## Manifest Setup

```toml
[install]
gcloud.pkg-path = "google-cloud-sdk"

[vars]
CLOUDSDK_CONFIG = "${FLOX_ENV_CACHE}/gcloud"
CLOUDSDK_CORE_PROJECT = "my-project-id"
GOOGLE_APPLICATION_CREDENTIALS = "${FLOX_ENV_CACHE}/gcloud/application_default_credentials.json"

[hook]
on-activate = """
  mkdir -p "$CLOUDSDK_CONFIG"

  # Check auth status, prompt if not authenticated
  if ! gcloud auth print-identity-token &>/dev/null 2>&1; then
    echo "GCP auth required. Run: gcloud auth login"
  fi

  # Ensure project is set
  gcloud config set project "$CLOUDSDK_CORE_PROJECT" 2>/dev/null || true
"""
```

## Authentication in Hooks

### User Authentication

For interactive development, validate auth on activation:

```toml
[hook]
on-activate = """
  mkdir -p "$CLOUDSDK_CONFIG"

  # Verify active account
  ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null)
  if [ -z "$ACTIVE_ACCOUNT" ]; then
    echo "No active GCP account. Run: gcloud auth login"
  else
    echo "GCP: authenticated as $ACTIVE_ACCOUNT"
  fi
"""
```

### Application Default Credentials

For services and local testing, set up ADC:

```bash
gcloud auth application-default login
# Credentials saved to $CLOUDSDK_CONFIG/application_default_credentials.json
```

The `GOOGLE_APPLICATION_CREDENTIALS` var in the manifest points libraries to the right file automatically.

### Service Account Keys

For CI or non-interactive contexts:

```toml
[hook]
on-activate = """
  if [ -n "$GCP_SA_KEY_PATH" ] && [ -f "$GCP_SA_KEY_PATH" ]; then
    gcloud auth activate-service-account --key-file="$GCP_SA_KEY_PATH"
  fi
"""
```

Never store service account key files in the manifest or repository.

## Project Switching

Scope GCP projects per Flox environment:

```toml
[vars]
CLOUDSDK_CORE_PROJECT = "my-staging-project"
CLOUDSDK_COMPUTE_REGION = "us-central1"
CLOUDSDK_COMPUTE_ZONE = "us-central1-a"
```

Override for a single session:

```bash
CLOUDSDK_CORE_PROJECT=my-prod-project flox activate
```

## Cloud Run Local Development

Develop Cloud Run services locally before deploying:

```toml
[install]
gcloud.pkg-path = "google-cloud-sdk"
docker.pkg-path = "docker"

[hook]
on-activate = """
  # Ensure Docker is available for Cloud Run local builds
  if ! docker info &>/dev/null; then
    echo "WARNING: Docker not running. Cloud Run local builds will fail."
  fi
"""
```

Build and test locally:

```bash
# Build container
docker build -t gcr.io/$CLOUDSDK_CORE_PROJECT/myservice:dev .

# Run locally with Cloud Run environment simulation
docker run -p 8080:8080 \
  -e PORT=8080 \
  -e K_SERVICE=myservice \
  gcr.io/$CLOUDSDK_CORE_PROJECT/myservice:dev
```

## GKE Cluster Access

Configure kubectl credentials for GKE clusters:

```toml
[install]
gcloud.pkg-path = "google-cloud-sdk"
kubectl.pkg-path = "kubectl"

[vars]
KUBECONFIG = "${FLOX_ENV_CACHE}/kubeconfig"
GKE_CLUSTER = "my-cluster"

[hook]
on-activate = """
  mkdir -p "$(dirname "$KUBECONFIG")"

  # Fetch GKE credentials if cluster is configured
  if [ -n "$GKE_CLUSTER" ] && gcloud auth print-identity-token &>/dev/null 2>&1; then
    gcloud container clusters get-credentials "$GKE_CLUSTER" \
      --region "$CLOUDSDK_COMPUTE_REGION" \
      --project "$CLOUDSDK_CORE_PROJECT" 2>/dev/null || true
  fi
"""
```

## Key Principles

- Set `CLOUDSDK_CONFIG` to `$FLOX_ENV_CACHE` -- isolates gcloud config per project
- Use `CLOUDSDK_CORE_PROJECT` in `[vars]` instead of `gcloud config set project`
- Validate auth in hooks but never block activation -- warn and continue
- Store ADC in `$FLOX_ENV_CACHE`, not `~/.config/gcloud`
- Never commit service account keys -- use env vars pointing to external paths

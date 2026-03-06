# GCP Diagnostic Patterns

## Auth Not Configured

**Symptoms:** `ERROR: (gcloud.auth.print-identity-token) You do not currently have an active account selected`, `Request had invalid authentication credentials`.

**Diagnostic steps:**
1. Check active accounts: `gcloud auth list`
2. Check config directory: `echo $CLOUDSDK_CONFIG`
3. Check application default credentials: `gcloud auth application-default print-access-token`
4. Check if config directory is populated: `ls "$CLOUDSDK_CONFIG"`

**Flox-specific causes:**
- `CLOUDSDK_CONFIG` set to `$FLOX_ENV_CACHE/gcloud` but no login performed in that config directory
- Auth tokens in `$FLOX_ENV_CACHE/gcloud` have expired (they expire after ~1 hour)
- Copied config from `~/.config/gcloud` but refresh tokens are tied to the original path

**Resolution pattern:**
```bash
# Login with Flox-scoped config
gcloud auth login

# For application default credentials (used by client libraries)
gcloud auth application-default login

# Verify
gcloud auth list
gcloud auth print-identity-token
```

## Project Not Set

**Symptoms:** `ERROR: (gcloud) The required property [project] is not currently set`, API calls return `PERMISSION_DENIED`.

**Diagnostic steps:**
1. Check current project: `gcloud config get-value project`
2. Check env var: `echo $CLOUDSDK_CORE_PROJECT`
3. List available projects: `gcloud projects list`

**Flox-specific causes:**
- `CLOUDSDK_CORE_PROJECT` not set in manifest `[vars]`
- Config directory in `$FLOX_ENV_CACHE` was freshly created and project not configured
- User has access to multiple projects and the wrong one is selected

**Resolution pattern:**
```bash
# Set project
gcloud config set project my-project-id

# Or add to manifest.toml [vars]
# CLOUDSDK_CORE_PROJECT = "my-project-id"

# Verify
gcloud config get-value project
```

## Quota Errors

**Symptoms:** `RESOURCE_EXHAUSTED`, `Quota exceeded for quota metric`, `rateLimitExceeded`.

**Diagnostic steps:**
1. Check which quota is exceeded: Error message includes the metric name
2. Check current usage: `gcloud compute project-info describe --project $CLOUDSDK_CORE_PROJECT`
3. For API rate limits: Implement exponential backoff

**Resolution pattern:**
```bash
# Check quotas for a specific region
gcloud compute regions describe us-central1 --project "$CLOUDSDK_CORE_PROJECT"

# Request quota increase via console (cannot be done via CLI)
echo "Visit: https://console.cloud.google.com/iam-admin/quotas"
```

## SDK Component Installation

**Symptoms:** `ERROR: (gcloud.components.install) You cannot perform this action because the Google Cloud CLI component manager is disabled for this installation`.

**Cause:** Flox installs `google-cloud-sdk` from Nixpkgs, which is read-only. The `gcloud components` manager cannot modify a Nix-managed installation.

**Resolution pattern:**
```bash
# Do NOT use gcloud components install/update
# Instead, check if the component is available as a separate Nix package

# Common components available as Flox packages:
# kubectl -> install kubectl separately in manifest
# docker-credential-gcr -> install separately
# cloud-sql-proxy -> install separately

# For alpha/beta commands, they are usually included in the SDK package
gcloud beta compute instances list  # Usually works without separate install
```

```toml
# Add needed tools as separate Flox packages instead
[install]
gcloud.pkg-path = "google-cloud-sdk"
kubectl.pkg-path = "kubectl"
```

## Application Default Credentials Not Found

**Symptoms:** `Could not automatically determine credentials`, `DefaultCredentialsError`.

**Diagnostic steps:**
1. Check `GOOGLE_APPLICATION_CREDENTIALS`: `echo $GOOGLE_APPLICATION_CREDENTIALS`
2. Check file exists: `ls -la "$GOOGLE_APPLICATION_CREDENTIALS"`
3. Check ADC login: `gcloud auth application-default print-access-token`

**Flox-specific causes:**
- `GOOGLE_APPLICATION_CREDENTIALS` points to `$FLOX_ENV_CACHE/gcloud/application_default_credentials.json` but ADC login was not performed
- Service account key file path is wrong

**Resolution pattern:**
```bash
# For development, use ADC
gcloud auth application-default login
# File will be created at $CLOUDSDK_CONFIG/application_default_credentials.json

# Verify
cat "$GOOGLE_APPLICATION_CREDENTIALS" | jq .type
```

## General Debugging Checklist

1. `gcloud auth list` -- shows authenticated accounts
2. `gcloud config get-value project` -- confirms project is set
3. `echo $CLOUDSDK_CONFIG` -- confirms Flox-scoped config directory
4. `gcloud info` -- full diagnostic output (config paths, SDK version, account)
5. `ls "$CLOUDSDK_CONFIG"` -- confirms config directory is populated
6. `gcloud auth print-identity-token` -- confirms valid auth token

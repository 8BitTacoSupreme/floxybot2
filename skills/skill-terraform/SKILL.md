# Terraform with Flox

Flox pins Terraform (or OpenTofu) versions per-project and manages provider caching, state file locations, and LocalStack integration through manifest hooks.

## Manifest Setup

```toml
[install]
terraform.pkg-path = "terraform"
terraform.version = "^1.8"
# Or use OpenTofu as a drop-in replacement:
# opentofu.pkg-path = "opentofu"
terragrunt.pkg-path = "terragrunt"

[vars]
TF_DATA_DIR = "${FLOX_ENV_CACHE}/terraform"
TF_PLUGIN_CACHE_DIR = "${FLOX_ENV_CACHE}/terraform/plugin-cache"

[hook]
on-activate = """
  # Create provider cache directory
  mkdir -p "$TF_PLUGIN_CACHE_DIR"

  # Set state file location for local backends
  export TF_STATE_DIR="$FLOX_ENV_CACHE/terraform/state"
  mkdir -p "$TF_STATE_DIR"
"""
```

## Provider Caching

Terraform downloads providers on every `init` by default. The `TF_PLUGIN_CACHE_DIR` variable tells Terraform to cache providers in `$FLOX_ENV_CACHE`, so they persist across activations and are shared across workspaces within the same project.

This is especially valuable for air-gapped or slow-network environments. The cache survives `flox delete` since `$FLOX_ENV_CACHE` is persistent.

## State File Management

For local development, keep state in `$FLOX_ENV_CACHE` to avoid committing it:

```hcl
terraform {
  backend "local" {
    path = "${TF_STATE_DIR}/terraform.tfstate"
  }
}
```

For team workflows, use a remote backend but keep the local `.terraform` directory in the cache:

```toml
[vars]
TF_DATA_DIR = "${FLOX_ENV_CACHE}/terraform"
```

## LocalStack Integration

Use LocalStack for local AWS development without incurring costs:

```toml
[install]
localstack.pkg-path = "localstack"

[services]
localstack.command = "localstack start"

[vars]
AWS_ENDPOINT_URL = "http://localhost:4566"
AWS_ACCESS_KEY_ID = "test"
AWS_SECRET_ACCESS_KEY = "test"
AWS_DEFAULT_REGION = "us-east-1"
```

Then configure your Terraform providers to use LocalStack:

```hcl
provider "aws" {
  endpoints {
    s3       = "http://localhost:4566"
    dynamodb = "http://localhost:4566"
    lambda   = "http://localhost:4566"
    iam      = "http://localhost:4566"
    sqs      = "http://localhost:4566"
  }
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}
```

**LocalStack free-tier limitations:** EKS, RDS clusters, EIP, and advanced IAM policy simulation are NOT supported. Check `LOCALSTACK-LIMITATIONS.md` if present in the project.

## Workspace Management

Use Flox vars to drive workspace selection:

```toml
[vars]
TF_WORKSPACE = "dev"

[hook]
on-activate = """
  terraform workspace select "$TF_WORKSPACE" 2>/dev/null || \
    terraform workspace new "$TF_WORKSPACE"
"""
```

## tfvars via Environment Variables

Terraform auto-reads `TF_VAR_*` environment variables. Set them in your manifest:

```toml
[vars]
TF_VAR_region = "us-west-2"
TF_VAR_environment = "dev"
TF_VAR_project_name = "myproject"
```

## Key Principles

- Always set `TF_PLUGIN_CACHE_DIR` to `$FLOX_ENV_CACHE` -- saves bandwidth and time
- Keep `.terraform` and state files out of the project tree using `TF_DATA_DIR`
- Use `TF_VAR_*` in `[vars]` instead of `.tfvars` files for environment-specific config
- Pin Terraform version in the manifest to prevent version drift across the team
- Guard workspace creation in hooks with existence checks

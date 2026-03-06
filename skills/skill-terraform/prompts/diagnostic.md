# Terraform Diagnostic Patterns

## State Lock Errors

**Symptoms:** `Error acquiring the state lock` or `ConditionalCheckFailedException`.

**Diagnostic steps:**
1. Check who holds the lock: Error message includes lock ID and holder info
2. Check if the previous operation crashed: `terraform force-unlock <LOCK_ID>`
3. For local state: Check for `.terraform.tfstate.lock.info` file

**Flox-specific causes:**
- Multiple `flox activate` sessions running `terraform apply` concurrently
- Previous activation crashed mid-apply, leaving a stale lock in `$FLOX_ENV_CACHE`
- `TF_DATA_DIR` pointing to a shared location across environments

**Resolution pattern:**
```bash
# Force unlock (use with caution)
terraform force-unlock <LOCK_ID>

# For local state, remove lock file directly
rm -f "$TF_DATA_DIR/.terraform.tfstate.lock.info"

# Verify state is consistent after unlock
terraform plan
```

## Provider Not Found

**Symptoms:** `provider registry.terraform.io/hashicorp/<name> was not found` or `Failed to install provider`.

**Diagnostic steps:**
1. Check provider block in `.tf` files for typos
2. Check network connectivity: `curl -I https://registry.terraform.io`
3. Check plugin cache: `ls $TF_PLUGIN_CACHE_DIR`
4. Run `terraform init -upgrade` to refresh providers

**Flox-specific causes:**
- `TF_PLUGIN_CACHE_DIR` pointing to a non-existent directory (hook didn't run)
- Cache corruption after Flox environment rebuild
- Network restrictions in the Flox environment

**Resolution pattern:**
```bash
# Verify cache directory exists
mkdir -p "$TF_PLUGIN_CACHE_DIR"

# Clear corrupted cache
rm -rf "$TF_PLUGIN_CACHE_DIR"/*

# Re-initialize
terraform init -upgrade
```

## Module Source Errors

**Symptoms:** `Error downloading modules` or `Failed to load module`.

**Common causes:**
- Git module source requires `git` in the Flox manifest
- Private module requires SSH key or token authentication
- Relative path modules break when `TF_DATA_DIR` is redirected

**Flox-specific causes:**
- `git` not installed in the manifest (needed for git-sourced modules)
- SSH agent not forwarded into the Flox environment
- Relative path `source = "../modules/foo"` calculated from wrong base when `TF_DATA_DIR` is set

**Resolution pattern:**
```toml
# Ensure git is available for module downloads
[install]
git.pkg-path = "git"
openssh.pkg-path = "openssh"
```

```bash
# For SSH-based module sources
eval $(ssh-agent)
ssh-add ~/.ssh/id_rsa
terraform init
```

## LocalStack Compatibility

**Symptoms:** Resources fail to create on LocalStack, API errors, unsupported operations.

**NOT supported on LocalStack free tier:**
- EKS (Elastic Kubernetes Service)
- EIP (Elastic IP)
- Advanced IAM policy simulation
- RDS clusters
- Most "enterprise" AWS features

**Diagnostic steps:**
1. Check if the resource type is supported: consult LocalStack docs
2. Check endpoint configuration in provider block
3. Verify LocalStack is running: `curl http://localhost:4566/_localstack/health`

**Resolution pattern:**
```bash
# Check LocalStack health
curl -s http://localhost:4566/_localstack/health | jq .

# Check if a specific service is available
curl -s http://localhost:4566/_localstack/health | jq '.services.s3'

# If a resource is not supported, mock it or skip it:
# Use count = var.use_localstack ? 0 : 1 to conditionally skip unsupported resources
```

## OpenTofu Compatibility

**Symptoms:** HashiCorp-licensed providers failing with OpenTofu.

**Resolution:**
- Most providers work identically with OpenTofu
- Check the OpenTofu registry for community-maintained providers
- Replace `terraform` with `tofu` in all commands
- State files are compatible between Terraform and OpenTofu

## General Debugging Checklist

1. Is `TF_PLUGIN_CACHE_DIR` set and the directory exists?
2. Is `TF_DATA_DIR` set? Does `.terraform` exist there?
3. Is the state file accessible? Check `TF_STATE_DIR` or remote backend config
4. Has `terraform init` been run in this environment?
5. Are all required environment variables set? `terraform plan` will error on missing vars
6. For LocalStack: Is the service running and healthy?

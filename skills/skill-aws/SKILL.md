# AWS with Flox

Flox manages AWS CLI tools, credential workflows, and local development with LocalStack through reproducible manifest configurations.

## Manifest Setup

```toml
[install]
awscli2.pkg-path = "awscli2"
aws-vault.pkg-path = "aws-vault"
aws-sam-cli.pkg-path = "aws-sam-cli"
ssm-plugin.pkg-path = "ssm-session-manager-plugin"

[vars]
AWS_DEFAULT_REGION = "us-west-2"
AWS_CONFIG_FILE = "${FLOX_ENV_CACHE}/aws/config"
AWS_SHARED_CREDENTIALS_FILE = "${FLOX_ENV_CACHE}/aws/credentials"

[hook]
on-activate = """
  mkdir -p "$FLOX_ENV_CACHE/aws"

  # Copy credentials from home if not yet cached
  if [ ! -f "$AWS_SHARED_CREDENTIALS_FILE" ] && [ -f "$HOME/.aws/credentials" ]; then
    cp "$HOME/.aws/credentials" "$AWS_SHARED_CREDENTIALS_FILE"
    cp "$HOME/.aws/config" "$AWS_CONFIG_FILE" 2>/dev/null || true
  fi
"""
```

## Credential Management

### Profile Switching

Use Flox vars to set the active AWS profile per project:

```toml
[vars]
AWS_PROFILE = "staging"
```

Switch profiles without editing the manifest by overriding at activation:

```bash
AWS_PROFILE=production flox activate
```

### SSO Authentication

Configure SSO auth that triggers on activation when credentials are expired:

```toml
[hook]
on-activate = """
  # Check if SSO session is valid, prompt login if expired
  if ! aws sts get-caller-identity &>/dev/null; then
    echo "AWS SSO session expired. Logging in..."
    aws sso login --profile "${AWS_PROFILE:-default}"
  fi
"""
```

### aws-vault Integration

For MFA-protected accounts, use aws-vault with the Flox keychain backend:

```toml
[vars]
AWS_VAULT_BACKEND = "file"
AWS_VAULT_FILE_DIR = "${FLOX_ENV_CACHE}/aws-vault"

[hook]
on-activate = """
  mkdir -p "$AWS_VAULT_FILE_DIR"
"""
```

## LocalStack for Local Development

Run AWS services locally without costs:

```toml
[install]
localstack.pkg-path = "localstack"

[services]
localstack.command = "localstack start"

[vars]
LOCALSTACK_ENDPOINT = "http://localhost:4566"

[hook]
on-activate = """
  # Create alias for local AWS commands
  floxbot_awslocal() {
    aws --endpoint-url "$LOCALSTACK_ENDPOINT" "$@"
  }
"""

[profile]
common = """
  floxbot_awslocal() {
    aws --endpoint-url "${LOCALSTACK_ENDPOINT:-http://localhost:4566}" "$@"
  }
"""
```

## SAM Local Development

AWS SAM for serverless functions uses Docker under the hood. Ensure Docker is available:

```toml
[install]
aws-sam-cli.pkg-path = "aws-sam-cli"
docker.pkg-path = "docker"

[hook]
on-activate = """
  # Validate Docker is running for SAM local
  if ! docker info &>/dev/null; then
    echo "WARNING: Docker not running. SAM local invoke/start-api will fail."
  fi
"""
```

Run SAM locally:

```bash
sam local invoke MyFunction --event event.json
sam local start-api --port 3000
```

## Key Principles

- Store AWS config/credentials in `$FLOX_ENV_CACHE`, not `~/.aws` -- keeps projects isolated
- Set `AWS_PROFILE` in `[vars]` for per-project account targeting
- Use hooks to validate credentials on activation -- catch auth issues early
- LocalStack free tier does NOT support EKS, RDS clusters, or advanced IAM
- Never store credentials in `manifest.toml` -- use environment variables or `$FLOX_ENV_CACHE`
- Use `aws-vault` for MFA workflows to avoid manual token entry

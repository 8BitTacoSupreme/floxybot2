# AWS Diagnostic Patterns

## Credential Errors

**Symptoms:** `Unable to locate credentials`, `ExpiredTokenException`, `InvalidClientTokenId`.

**Diagnostic steps:**
1. Check active credentials: `aws sts get-caller-identity`
2. Check credential chain: `AWS_PROFILE`, env vars, credential file, instance metadata
3. Check file locations: `echo $AWS_SHARED_CREDENTIALS_FILE` and `echo $AWS_CONFIG_FILE`
4. Check expiration: SSO and assumed-role credentials expire

**Flox-specific causes:**
- `AWS_SHARED_CREDENTIALS_FILE` set to `$FLOX_ENV_CACHE/aws/credentials` but file not copied from `~/.aws`
- Credentials copied at environment creation are now expired
- `AWS_PROFILE` set in manifest but that profile does not exist in the Flox-scoped credentials file
- aws-vault session expired

**Resolution pattern:**
```bash
# Check what's configured
aws configure list

# For SSO
aws sso login --profile "$AWS_PROFILE"

# For static credentials, recopy from home
cp ~/.aws/credentials "$AWS_SHARED_CREDENTIALS_FILE"
cp ~/.aws/config "$AWS_CONFIG_FILE"

# For aws-vault
aws-vault exec "$AWS_PROFILE" -- aws sts get-caller-identity
```

## Region Not Set

**Symptoms:** `You must specify a region`, `Could not connect to the endpoint URL`.

**Diagnostic steps:**
1. Check: `echo $AWS_DEFAULT_REGION` and `echo $AWS_REGION`
2. Check config file: `grep region "$AWS_CONFIG_FILE"`
3. Check the profile section matches `$AWS_PROFILE`

**Flox-specific causes:**
- `AWS_DEFAULT_REGION` not set in manifest `[vars]`
- Config file has region under a profile that doesn't match `$AWS_PROFILE`

**Resolution pattern:**
```toml
# Add to manifest.toml
[vars]
AWS_DEFAULT_REGION = "us-west-2"
```

```bash
# Or set temporarily
export AWS_DEFAULT_REGION=us-west-2
```

## MFA Token Issues

**Symptoms:** `MultiFactorAuthentication failed`, `Access Denied` with valid credentials.

**Diagnostic steps:**
1. Check if the role requires MFA: look at trust policy
2. Check aws-vault is configured: `aws-vault list`
3. Check token expiration

**Resolution pattern:**
```bash
# Use aws-vault for MFA
aws-vault exec my-profile -- aws s3 ls

# Or manually assume role with MFA
aws sts assume-role \
  --role-arn arn:aws:iam::123456789:role/MyRole \
  --role-session-name flox-session \
  --serial-number arn:aws:iam::123456789:mfa/myuser \
  --token-code <MFA_CODE>
```

## LocalStack Endpoint Configuration

**Symptoms:** Commands hitting real AWS instead of LocalStack, or connection refused to localhost.

**Diagnostic steps:**
1. Check LocalStack is running: `curl http://localhost:4566/_localstack/health`
2. Check endpoint override: `echo $AWS_ENDPOINT_URL`
3. Check per-service endpoints if using older configuration style

**Flox-specific causes:**
- LocalStack service not started (check `flox services status`)
- `AWS_ENDPOINT_URL` not set in manifest `[vars]`
- Port conflict: another service using 4566

**Resolution pattern:**
```bash
# Check LocalStack health
curl -s http://localhost:4566/_localstack/health | jq .

# Verify endpoint is set
echo $AWS_ENDPOINT_URL

# Use explicit endpoint for a single command
aws --endpoint-url http://localhost:4566 s3 ls
```

**LocalStack free-tier limitations (do NOT try to debug these -- they simply are not supported):**
- EKS
- RDS clusters
- EIP
- Advanced IAM policy simulation

## SSO Login Failures

**Symptoms:** `Error when retrieving token from SSO`, browser does not open, `InvalidGrantException`.

**Diagnostic steps:**
1. Check SSO configuration: `aws configure sso`
2. Check browser availability (needed for SSO login)
3. Check SSO start URL and region in config

**Flox-specific causes:**
- Config file in `$FLOX_ENV_CACHE/aws/config` missing SSO section
- Browser cannot be launched from the Flox shell (headless environment)

**Resolution pattern:**
```bash
# Reconfigure SSO in the Flox-scoped config
aws configure sso --config-file "$AWS_CONFIG_FILE"

# For headless environments, use the no-browser flow
aws sso login --profile "$AWS_PROFILE" --no-browser
```

## General Debugging Checklist

1. `aws sts get-caller-identity` -- confirms auth works and shows account/role
2. `echo $AWS_DEFAULT_REGION` -- confirms region is set
3. `echo $AWS_PROFILE` -- confirms correct profile
4. `cat "$AWS_CONFIG_FILE"` -- confirms config file is populated
5. `aws configure list` -- shows full credential chain resolution
6. For LocalStack: `curl -s http://localhost:4566/_localstack/health`

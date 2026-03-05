# Core Flox Canon

This is the foundational skill package for FloxBot. It covers core Flox concepts,
commands, and workflows that every Flox user needs.

## Key Topics

### Environment Management
- `flox init` — Initialize a new Flox environment
- `flox activate` — Activate an environment
- `flox install <pkg>` — Install a package
- `flox search <query>` — Search the catalog
- `flox show <pkg>` — Show package details
- `flox edit` — Edit the manifest directly
- `flox delete` — Delete an environment

### Manifest (manifest.toml)
- `[install]` — Package declarations
- `[vars]` — Environment variables
- `[hook]` — Activation hooks (bash)
- `[profile]` — Shell profile scripts
- `[services]` — Background services
- `[include]` — Environment composition
- `[build]` — Package build definitions
- `[options]` — System and CUDA options

### Sharing & Collaboration
- `flox push` — Push environment to FloxHub
- `flox pull` — Pull environment from FloxHub
- `flox list -r` — List remote environment packages

### Building & Publishing
- `flox build` — Build a package from manifest
- `flox publish` — Publish to FloxHub catalog

## Common Patterns

### Python Development
```toml
[install]
python3.pkg-path = "python3"
python3.version = "^3.12"

[hook]
on-activate = """
  if [ ! -d "$FLOX_ENV_CACHE/venv" ]; then
    python3 -m venv "$FLOX_ENV_CACHE/venv"
  fi
"""

[profile]
common = """
  source "$FLOX_ENV_CACHE/venv/bin/activate"
"""
```

### Node.js Development
```toml
[install]
nodejs.pkg-path = "nodejs"
nodejs.version = "^20"

[vars]
NODE_ENV = "development"
```

### Services
```toml
[services]
api.command = "uvicorn main:app --reload --port 8000"
worker.command = "celery -A worker worker --loglevel=info"
```

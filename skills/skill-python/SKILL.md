# Python with Flox

Flox manages Python interpreters and system-level dependencies while integrating with Python's own package ecosystem (pip, venv, uv, poetry). This guide covers how to combine Flox packages with Python virtual environments.

## Manifest Setup

```toml
[install]
python3.pkg-path = "python3"
python3.version = "^3.12"
uv.pkg-path = "uv"
ruff.pkg-path = "ruff"
mypy.pkg-path = "mypy"

[vars]
VIRTUAL_ENV = "${FLOX_ENV_CACHE}/venv"
PIP_CACHE_DIR = "${FLOX_ENV_CACHE}/pip-cache"
UV_CACHE_DIR = "${FLOX_ENV_CACHE}/uv-cache"

[hook]
on-activate = """
  # Create venv if it does not exist
  if [ ! -d "$VIRTUAL_ENV" ]; then
    echo "Creating Python venv..."
    python3 -m venv "$VIRTUAL_ENV"
  fi

  mkdir -p "$PIP_CACHE_DIR"
"""

[profile]
common = """
  source "$VIRTUAL_ENV/bin/activate"
"""
```

## venv Alongside Flox

Flox provides the Python interpreter and system libraries. The venv handles Python-only packages (from PyPI). This separation is intentional:

- **Flox `[install]`**: Python interpreter, system libraries (openssl, libpq, etc.), CLI tools (ruff, mypy)
- **venv/pip/uv**: Pure Python packages (fastapi, requests, pydantic, etc.)

The venv lives in `$FLOX_ENV_CACHE/venv` so it:
- Persists across activations
- Stays project-scoped
- Does not conflict with other Flox environments
- Survives `flox delete`

### venv Activation Order

The `[profile]` section runs AFTER `[hook]`, so the venv is created in the hook and activated in the profile. This ensures the venv exists before activation is attempted.

## uv for Fast Installs

uv is a drop-in replacement for pip that is 10-100x faster:

```bash
# Inside flox activate (venv is already active)
uv pip install -r requirements.txt
uv pip install fastapi uvicorn
```

Cache uv downloads in `$FLOX_ENV_CACHE`:

```toml
[vars]
UV_CACHE_DIR = "${FLOX_ENV_CACHE}/uv-cache"
```

## pyproject.toml Alongside manifest.toml

A Python project typically has both files at the root:

```
myproject/
  .flox/env/manifest.toml   # Flox: interpreter, system libs, tools
  pyproject.toml             # Python: pip packages, project metadata
  src/
```

Install Python dependencies on activation:

```toml
[hook]
on-activate = """
  if [ ! -d "$VIRTUAL_ENV" ]; then
    python3 -m venv "$VIRTUAL_ENV"
  fi

  # Auto-install Python deps if requirements changed
  REQS_HASH=$(md5sum requirements.txt 2>/dev/null | cut -d' ' -f1 || echo "none")
  LAST_HASH=$(cat "$FLOX_ENV_CACHE/.reqs_hash" 2>/dev/null || echo "")
  if [ "$REQS_HASH" != "$LAST_HASH" ]; then
    "$VIRTUAL_ENV/bin/pip" install -r requirements.txt -q
    echo "$REQS_HASH" > "$FLOX_ENV_CACHE/.reqs_hash"
  fi
"""
```

## Poetry Integration

If the project uses Poetry:

```toml
[install]
python3.pkg-path = "python3"
python3.version = "^3.12"
poetry.pkg-path = "poetry"

[vars]
POETRY_VIRTUALENVS_PATH = "${FLOX_ENV_CACHE}/poetry-venvs"
POETRY_CACHE_DIR = "${FLOX_ENV_CACHE}/poetry-cache"

[hook]
on-activate = """
  mkdir -p "$POETRY_VIRTUALENVS_PATH" "$POETRY_CACHE_DIR"
  # Let Poetry manage its own venv, but cache it in FLOX_ENV_CACHE
  poetry install --no-interaction 2>/dev/null || true
"""
```

## System Packages vs pip Packages

Some Python packages need C libraries. Install them through Flox, not pip:

```toml
[install]
# System libraries for Python C extensions
openssl.pkg-path = "openssl"
openssl-dev.pkg-path = "openssl.dev"
libffi.pkg-path = "libffi"
libpq.pkg-path = "postgresql.lib"
pkg-config.pkg-path = "pkg-config"
```

Common mappings:

| pip package | Flox system dependency |
|-------------|----------------------|
| psycopg2 | `postgresql.lib`, `postgresql` |
| cryptography | `openssl`, `openssl.dev` |
| pillow | `libjpeg`, `zlib`, `libtiff` |
| lxml | `libxml2`, `libxslt` |
| numpy (from source) | `openblas`, `gfortran` |

## Flox Services for Python Apps

```toml
[services]
api.command = "uvicorn main:app --reload --host 0.0.0.0 --port 8000"
worker.command = "celery -A tasks worker --loglevel=info"
scheduler.command = "celery -A tasks beat --loglevel=info"
```

## Key Principles

- Create venvs in `$FLOX_ENV_CACHE/venv` -- never in the project directory
- Create the venv in `[hook]`, activate it in `[profile]` (ordering matters)
- Use Flox `[install]` for the interpreter and system C libraries
- Use pip/uv/poetry for pure Python packages inside the venv
- Cache pip/uv downloads in `$FLOX_ENV_CACHE` to speed up reinstalls
- If `pip install` fails with "C extension" errors, install the system library via Flox
- Never use system pip (`/usr/bin/pip`) -- always use the venv pip

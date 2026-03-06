# Python Diagnostic Patterns

## Module Not Found (System vs venv)

**Symptoms:** `ModuleNotFoundError: No module named 'foo'`, package installed but import fails.

**Diagnostic steps:**
1. Check which Python: `which python3` and `which pip`
2. Check if venv is active: `echo $VIRTUAL_ENV`
3. Check where package is installed: `pip show foo`
4. Check sys.path: `python3 -c "import sys; print('\n'.join(sys.path))"`

**Flox-specific causes:**
- venv not activated (profile section didn't run, or using `on-activate` instead of `profile`)
- Package installed with system pip (`/usr/bin/pip`) instead of venv pip
- Package installed before `flox activate`, so it's in `~/.local/lib` not the venv
- Flox-provided Python shadowing the venv Python (wrong PATH order)

**Resolution pattern:**
```bash
# Verify venv is active
echo $VIRTUAL_ENV  # Should point to $FLOX_ENV_CACHE/venv

# Check which pip is running
which pip  # Should be $VIRTUAL_ENV/bin/pip

# Reinstall in the correct venv
pip install foo

# If venv activation is missing, check manifest.toml:
# [profile]
# common = 'source "$VIRTUAL_ENV/bin/activate"'
```

## pip Install Failures

**Symptoms:** `Failed building wheel`, `error: subprocess-exited-with-error`, `No matching distribution found`.

### C Extension Build Failures

**Diagnostic steps:**
1. Read the full error: look for `gcc` or `cc` errors, missing headers
2. Check for system library requirements: `-lssl`, `-lpq`, `-lffi`
3. Check if `pkg-config` is available: `which pkg-config`

**Flox-specific causes:**
- System library needed by C extension not in Flox manifest
- Headers (`.dev` package) not installed alongside the library
- `pkg-config` not in manifest

**Resolution pattern:**
```toml
# Common C extension dependencies
[install]
# For psycopg2
postgresql.pkg-path = "postgresql"
postgresql-lib.pkg-path = "postgresql.lib"

# For cryptography
openssl.pkg-path = "openssl"
openssl-dev.pkg-path = "openssl.dev"

# For Pillow
libjpeg.pkg-path = "libjpeg"
zlib.pkg-path = "zlib"

# Always include pkg-config
pkg-config.pkg-path = "pkg-config"
```

### Version Not Found

```bash
# Check available versions
pip index versions foo

# Use uv for better version resolution
uv pip install foo
```

## Version Conflicts

**Symptoms:** `ERROR: pip's dependency resolver does not currently consider all the packages`, `Conflicting dependencies`.

**Diagnostic steps:**
1. Check installed versions: `pip list`
2. Check for conflicts: `pip check`
3. Check requirements files for pins

**Resolution pattern:**
```bash
# Use uv for better dependency resolution
uv pip install -r requirements.txt

# Or rebuild the venv from scratch
rm -rf "$VIRTUAL_ENV"
python3 -m venv "$VIRTUAL_ENV"
source "$VIRTUAL_ENV/bin/activate"
pip install -r requirements.txt
```

## C Extension Build Failures

**Symptoms:** `error: command 'gcc' failed`, `fatal error: Python.h: No such file or directory`.

**Diagnostic steps:**
1. Check for Python headers: `python3-config --includes`
2. Check gcc/cc is available: `which gcc`
3. Check library paths: `echo $LIBRARY_PATH`

**Flox-specific causes:**
- Python development headers not findable (rare with Flox-provided Python)
- C compiler not in the manifest
- Library installed but not linked properly

**Resolution pattern:**
```toml
[install]
python3.pkg-path = "python3"
gcc.pkg-path = "gcc"
pkg-config.pkg-path = "pkg-config"
```

```bash
# Verify Python headers are available
python3-config --includes
# Should show: -I/nix/store/.../include/python3.12
```

## venv Activation Conflicts with Flox

**Symptoms:** Wrong Python version used, PATH shows unexpected order, `deactivate` breaks Flox environment.

**Diagnostic steps:**
1. Check PATH order: `echo $PATH | tr ':' '\n' | head -10`
2. Check which Python wins: `which -a python3`
3. Check if multiple venvs are active

**Flox-specific causes:**
- venv activated in `[hook]` instead of `[profile]` (hook runs before PATH is finalized)
- Manual `source venv/bin/activate` in a separate venv conflicting with Flox-managed venv
- `deactivate` removing Flox-set PATH entries

**Resolution pattern:**
```toml
# CORRECT: Create in hook, activate in profile
[hook]
on-activate = """
  if [ ! -d "$VIRTUAL_ENV" ]; then
    python3 -m venv "$VIRTUAL_ENV"
  fi
"""

[profile]
common = """
  source "$VIRTUAL_ENV/bin/activate"
"""

# WRONG: Do not activate venv in [hook]
# [hook]
# on-activate = 'source "$VIRTUAL_ENV/bin/activate"'  # BAD
```

## Poetry-Specific Issues

**Symptoms:** `No module named poetry`, poetry creates venv in wrong location, poetry ignores Flox Python.

**Resolution pattern:**
```toml
[vars]
POETRY_VIRTUALENVS_PATH = "${FLOX_ENV_CACHE}/poetry-venvs"
POETRY_CACHE_DIR = "${FLOX_ENV_CACHE}/poetry-cache"
# Tell Poetry to use Flox-provided Python
POETRY_VIRTUALENVS_PREFER_ACTIVE_PYTHON = "true"
```

## General Debugging Checklist

1. `which python3` -- is it the Flox Python or system Python?
2. `which pip` -- is it the venv pip?
3. `echo $VIRTUAL_ENV` -- is the venv active?
4. `pip check` -- are there dependency conflicts?
5. `python3 -c "import sys; print(sys.prefix)"` -- confirms active Python prefix
6. `pkg-config --list-all` -- available system libraries for C extensions

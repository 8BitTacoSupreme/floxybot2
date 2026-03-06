# PostgreSQL Diagnostic Patterns

## Data Directory Permissions

**Symptoms:** `FATAL: data directory has wrong ownership`, `initdb: could not change permissions of directory`, `pg_ctl: could not start server`.

**Diagnostic steps:**
1. Check ownership: `ls -la "$PGDATA"`
2. Check permissions: Postgres requires 700 on the data directory
3. Check disk space: `df -h "$FLOX_ENV_CACHE"`

**Flox-specific causes:**
- `$PGDATA` directory created with wrong permissions by a previous hook run
- Another user activated the same Flox environment and created `$FLOX_ENV_CACHE`
- `initdb` ran as root but `pg_ctl` runs as normal user (or vice versa)

**Resolution pattern:**
```bash
# Fix permissions
chmod 700 "$PGDATA"

# If ownership is wrong and you own the cache directory
# the safest fix is to reinitialize
rm -rf "$PGDATA"
initdb -D "$PGDATA" --no-locale --encoding=UTF8

# Reconfigure socket directory
echo "unix_socket_directories = '$PGDATA'" >> "$PGDATA/postgresql.conf"
```

## Port Conflicts

**Symptoms:** `FATAL: could not bind to address`, `port 5432 already in use`, `could not create listen socket`.

**Diagnostic steps:**
1. Check what's using the port: `lsof -i :5432` or `ss -tlnp | grep 5432`
2. Check for system PostgreSQL: `systemctl status postgresql`
3. Check for other Flox environments running postgres

**Flox-specific causes:**
- System PostgreSQL running on the default port
- Another Flox environment's postgres service is still running
- Previous `flox activate` session didn't clean up the postgres process

**Resolution pattern:**
```bash
# Use a different port in manifest.toml
# PGPORT = "5433"

# Or stop the conflicting service
sudo systemctl stop postgresql  # System postgres
flox services stop postgres     # Flox-managed postgres

# Kill orphaned postgres processes
pg_ctl stop -D "$PGDATA" -m immediate
# Or if pg_ctl doesn't work
pkill -f "postgres.*$PGDATA"
```

## Extension Not Found

**Symptoms:** `ERROR: could not open extension control file`, `extension "vector" is not available`.

**Diagnostic steps:**
1. Check installed extensions: `psql -h "$PGDATA" -c "SELECT * FROM pg_available_extensions;"`
2. Check the Flox package name matches the PostgreSQL version
3. Check shared_preload_libraries in postgresql.conf

**Flox-specific causes:**
- pgvector installed as `pgvector` but needs to be `postgresql16Packages.pgvector` (version-matched)
- Extension package version doesn't match the PostgreSQL major version
- Extension installed after database initialization, requires server restart

**Resolution pattern:**
```toml
# Correct: version-matched extension package
[install]
postgresql.pkg-path = "postgresql_16"
pgvector.pkg-path = "postgresql16Packages.pgvector"

# NOT: pgvector.pkg-path = "pgvector" (won't match the server)
```

```bash
# After adding extension package, restart and create extension
pg_ctl restart -D "$PGDATA"
psql -h "$PGDATA" -d devdb -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

## Connection Refused

**Symptoms:** `psql: error: connection to server failed: Connection refused`, `could not connect to server`.

**Diagnostic steps:**
1. Check server is running: `pg_ctl status -D "$PGDATA"`
2. Check socket exists: `ls "$PGDATA"/.s.PGSQL.*`
3. Check PGHOST matches socket location: `echo $PGHOST`
4. Check pg_hba.conf for allowed connections
5. Check server logs: `cat "$FLOX_ENV_CACHE/postgres.log"`

**Flox-specific causes:**
- `PGHOST` not set to `$PGDATA` (where Unix socket lives)
- Server never started (hook failed silently)
- Server started but crashed (check logs)
- Using `localhost` which tries TCP, but only Unix socket is configured

**Resolution pattern:**
```bash
# Check server status
pg_ctl status -D "$PGDATA"

# Check logs for errors
tail -20 "$FLOX_ENV_CACHE/postgres.log"

# Connect via Unix socket explicitly
psql -h "$PGDATA" -d devdb

# If server isn't running, start it
pg_ctl start -D "$PGDATA" -l "$FLOX_ENV_CACHE/postgres.log" -o "-k $PGDATA"
```

## pg_hba.conf Issues

**Symptoms:** `FATAL: no pg_hba.conf entry for host`, `FATAL: Peer authentication failed`.

**Cause:** pg_hba.conf controls who can connect and how they authenticate.

**Resolution pattern:**
```bash
# Check current pg_hba.conf
cat "$PGDATA/pg_hba.conf"

# For local dev, allow trust auth for local connections
cat >> "$PGDATA/pg_hba.conf" << 'EOF'
local   all   all                 trust
host    all   all   127.0.0.1/32  trust
host    all   all   ::1/128       trust
EOF

# Reload config (no restart needed for pg_hba changes)
pg_ctl reload -D "$PGDATA"
```

## General Debugging Checklist

1. `pg_ctl status -D "$PGDATA"` -- is the server running?
2. `echo $PGHOST $PGPORT $PGDATABASE` -- are connection vars correct?
3. `ls "$PGDATA"/.s.PGSQL.*` -- does the Unix socket exist?
4. `tail -20 "$FLOX_ENV_CACHE/postgres.log"` -- what do the logs say?
5. `cat "$PGDATA/pg_hba.conf"` -- is the connection allowed?
6. `df -h "$FLOX_ENV_CACHE"` -- is there disk space?

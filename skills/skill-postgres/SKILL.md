# PostgreSQL with Flox

Flox can run PostgreSQL as a managed service with data stored in `$FLOX_ENV_CACHE`, making databases project-scoped, portable, and reproducible.

## Manifest Setup

```toml
[install]
postgresql.pkg-path = "postgresql_16"
pgcli.pkg-path = "pgcli"
pgformatter.pkg-path = "pgformatter"

[vars]
PGDATA = "${FLOX_ENV_CACHE}/pgdata"
PGHOST = "${FLOX_ENV_CACHE}/pgdata"
PGPORT = "5432"
PGDATABASE = "devdb"

[hook]
on-activate = """
  # Initialize database cluster if not present
  if [ ! -d "$PGDATA/base" ]; then
    echo "Initializing PostgreSQL database..."
    initdb -D "$PGDATA" --no-locale --encoding=UTF8
    # Use Unix socket in the data directory (no TCP needed for local dev)
    echo "unix_socket_directories = '$PGDATA'" >> "$PGDATA/postgresql.conf"
    echo "port = $PGPORT" >> "$PGDATA/postgresql.conf"
  fi
"""

[services]
postgres.command = "pg_ctl start -D $PGDATA -l $FLOX_ENV_CACHE/postgres.log -o '-k $PGDATA' && tail -f $FLOX_ENV_CACHE/postgres.log"
postgres.shutdown = "pg_ctl stop -D $PGDATA -m fast"
```

## Data Directory Management

The data directory lives in `$FLOX_ENV_CACHE/pgdata`. This means:
- Data persists across `flox activate` sessions
- Data survives `flox delete` (cache is persistent)
- Each project gets its own isolated database
- No conflicts with system PostgreSQL installations

### Creating the Dev Database

Add database creation to the hook, guarded by an existence check:

```toml
[hook]
on-activate = """
  if [ ! -d "$PGDATA/base" ]; then
    initdb -D "$PGDATA" --no-locale --encoding=UTF8
    echo "unix_socket_directories = '$PGDATA'" >> "$PGDATA/postgresql.conf"
  fi

  # Start temporarily to create the database, then stop (service will manage it)
  if [ ! -f "$FLOX_ENV_CACHE/.db_created" ]; then
    pg_ctl start -D "$PGDATA" -l "$FLOX_ENV_CACHE/postgres-init.log" -o "-k $PGDATA" -w
    createdb -h "$PGDATA" "$PGDATABASE" 2>/dev/null || true
    pg_ctl stop -D "$PGDATA" -m fast
    touch "$FLOX_ENV_CACHE/.db_created"
  fi
"""
```

## pgvector Extension

For vector similarity search (used by RAG pipelines, embeddings):

```toml
[install]
postgresql.pkg-path = "postgresql_16"
pgvector.pkg-path = "postgresql16Packages.pgvector"
```

Enable in the database after starting:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE embeddings (
  id SERIAL PRIMARY KEY,
  content TEXT,
  embedding vector(1536)
);

CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops);
```

## Connection Management

### Unix Socket (Recommended for Local Dev)

Using Unix sockets avoids port conflicts and authentication complexity:

```bash
psql -h $PGDATA -d devdb
# Or with pgcli for a better interactive experience:
pgcli -h $PGDATA -d devdb
```

### TCP (When Needed)

If other services need TCP access, configure `pg_hba.conf`:

```toml
[hook]
on-activate = """
  if [ ! -d "$PGDATA/base" ]; then
    initdb -D "$PGDATA" --no-locale --encoding=UTF8
    cat >> "$PGDATA/postgresql.conf" <<PGCONF
listen_addresses = 'localhost'
port = $PGPORT
unix_socket_directories = '$PGDATA'
PGCONF
    # Allow local TCP connections without password for dev
    echo "host all all 127.0.0.1/32 trust" >> "$PGDATA/pg_hba.conf"
  fi
"""
```

## Backup and Restore

```bash
# Backup
pg_dump -h "$PGDATA" devdb > "$FLOX_ENV_CACHE/backup.sql"

# Restore
psql -h "$PGDATA" devdb < "$FLOX_ENV_CACHE/backup.sql"

# Binary backup for large databases
pg_basebackup -h "$PGDATA" -D "$FLOX_ENV_CACHE/pg_backup" -Ft -z
```

## Key Principles

- Always use `$FLOX_ENV_CACHE/pgdata` for `PGDATA` -- never a hardcoded path
- Set `PGHOST` to the socket directory for seamless `psql` usage
- Guard `initdb` with a check for `$PGDATA/base` directory
- Use Unix sockets for local dev to avoid port conflicts
- Install pgvector via `postgresql16Packages.pgvector` (version-matched)
- Use Flox services for start/stop lifecycle management

# Database: location & migration strategy

RedForge uses **SQLite** via SQLAlchemy 2.0 async (`aiosqlite`). This document is
the single source of truth for *where* the database lives and *how* its schema
evolves.

## Location (deterministic)

The database URL is resolved once at startup by
`app.config._resolve_database_url()`, in this order:

1. **`REDFORGE_DATABASE_URL`** — if set, used verbatim (power users, tests, an
   external DB path).
2. **Legacy `./redforge.db`** — if a file already exists in the current working
   directory, it is used. This keeps existing installs pointing at their data
   (backwards compatible) rather than silently starting a fresh DB.
3. **OS app-data directory** (the new default for fresh installs) —
   - Windows: `%LOCALAPPDATA%\RedForge\redforge.db`
   - macOS: `~/Library/Application Support/RedForge/redforge.db`
   - Linux: `$XDG_DATA_HOME/RedForge/redforge.db` (or `~/.local/share/RedForge/`)

The directory is created if missing. The result is an **absolute** path, so the
database no longer depends on the launch directory — the long-standing
CWD-relative ambiguity is gone.

## Migration strategy: `create_all` is canonical

RedForge builds its schema with **`Base.metadata.create_all`** at startup
(`init_db()` in `app/db/database.py`). This is the **single, authoritative**
schema source.

- **Additive changes are safe and automatic.** `create_all` creates any missing
  tables on the next start. Every V2 table (projects, datasets, dataset_versions,
  training_runs, checkpoints) landed this way with **no migration step**.
- **Startup job recovery** (`_recover_orphaned_jobs`) runs after `init_db`, so an
  upgraded DB is reconciled immediately.

### Why not Alembic (at runtime)

Alembic migration files exist under `backend/alembic/` from earlier development,
but **they are not run at startup and are not the source of truth.** Running both
would risk drift (a column present in a migration but absent from the model, or
vice-versa). To avoid that ambiguity:

- **The ORM models in `app/db/models.py` are canonical.** Add a column → it
  exists after the next start.
- Alembic is retained only for **explicit, destructive migrations** a maintainer
  runs by hand (e.g. renaming/dropping a column, which `create_all` cannot do).
  Such changes must also update the model so `create_all` stays in parity.

### Upgrade safety rules

- **Only add** columns/tables between releases (additive) → zero-touch upgrades.
- **Never rename or drop** a column in a release without an explicit Alembic
  migration *and* a matching model change, plus a note in the CHANGELOG.
- New nullable columns (or columns with a server/default value) are always safe.
- A future schema-parity test (recommended) should assert that `create_all`'s
  output matches the latest Alembic head, catching drift in CI.

## Backups & portability

The database is a single SQLite file at the resolved path — copy it to back up,
move it (and set `REDFORGE_DATABASE_URL`) to relocate. Nothing leaves the machine.

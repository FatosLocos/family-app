# Security Architecture

## Row-Level Security (RLS) Boundary

Family App enforces security at multiple layers. This document defines the **database-level security boundary** and the trust model.

### Multi-Role Database Architecture

Family App uses a **two-role separation** in PostgreSQL:

1. **Owner Role** (`{APP_DB_USER}_owner` by default)
   - Nologin role; never used by the application directly
   - **Owns** the schema, all tables, views, sequences, and RLS policies
   - Has full DDL permissions (ALTER, DROP, CREATE, etc.)
   - Used only by DBAs and deployment automation

2. **App Role** (`{APP_DB_USER}`)
   - Login role; used by the Django application
   - Has **only DML permissions**: SELECT, INSERT, UPDATE, DELETE
   - Cannot modify table structure, disable RLS, or run DDL
   - Enforced at the PostgreSQL level

### RLS Guarantee

When RLS is enforced on a table:
- Django queries run as the app role
- App role cannot `ALTER TABLE ... DISABLE ROW LEVEL SECURITY` (no DDL permission)
- Even with a compromised database connection, the app role cannot bypass RLS via DDL

**Note:** The superuser (via `postgres` role) can always disable RLS. This is a PostgreSQL design principle. Superuser access must be protected as a separate risk.

### Restricted Tables (No RLS Policies)

Three tables intentionally have no RLS policies:

- `identity_user`: Users are global; authentication bypass would expose all users
- `households_household`: Households are the isolation boundary; a household leak exposes family structure
- `households_householdinvite`: Invite codes are sensitive; leakage enables account hijacking

**Access Control**: These tables are NOT protected by RLS policies. They rely on:
- Django application-level filtering (checks `request.household` before any query)
- RLS policies on dependent tables (e.g., `household.FamilyMember` has RLS referencing `household_id`)

**Risk Assessment**: A compromised app role can query these tables. Mitigation:
1. App role has no direct login (database connections use the app role, not superuser)
2. All queries run through Django ORM, which enforces household scoping
3. Encrypted sensitive fields (invite code hashes use PBKDF2-SHA256)

### Audit & Monitoring

Monitor for unexpected queries:
1. Log connections as the app role (PostgreSQL `log_statement`)
2. Alert on DDL attempts by the app role (will fail due to permissions)
3. Track sensitive queries on `identity_user`, `households_household` (use view-level triggers if needed)

## Invite Code Hashing

Invite codes are hashed with **PBKDF2-SHA256** (100k iterations) before storage. Never store plaintext codes.

```python
from households.code_utils import verify_invite_code
if verify_invite_code(submitted_code, stored_hash):
    # Code is valid
```

## Deployment Notes

### Environment Variables

```bash
# Standard app credentials (already required)
APP_DB_NAME=family_app
APP_DB_USER=family_app
APP_DB_PASSWORD=<random>

# Owner role (optional; defaults to {APP_DB_USER}_owner)
APP_DB_OWNER=family_app_owner
```

### Database Initialization

- `ops/init-postgres.sh` creates both roles, grants the app role CONNECT + USAGE
  on schema `public` (the `REVOKE ALL ... FROM public` step also revokes the
  default public CONNECT grant, so it must be re-granted explicitly or the app
  role cannot log in at all), and sets default privileges so the owner role's
  future tables are automatically readable/writable by the app role.
- `ops/restore.sh` restores a backup (via the postgres superuser, `--no-owner`)
  and then reassigns every restored table/view/sequence/function to the owner
  role and re-grants DML to the app role, since `pg_restore` otherwise leaves
  everything owned by whichever role ran the restore.

### Why migrations need a different connection string

Since the app role has no DDL rights, `manage.py migrate` cannot run under the
same `DATABASE_URL` used at runtime. The `web` service in
`docker-compose.django.yml` sets a separate `MIGRATE_DATABASE_URL`: it connects
as the `postgres` superuser but with `options=-c role=<owner role>`, so
Postgres switches the session's `current_user` to the owner role for the
duration of the connection - every table `migrate` creates ends up owned by
the owner role, not the superuser, matching the runtime GRANTs. Only the
`migrate` step in the `web` container's startup command uses this DSN;
`collectstatic`, Daphne, Celery, and the listener services all use the normal
app-role `DATABASE_URL`.

Two pre-existing migrations (`integrations/migrations/0008_local_probe_application_owner.py`,
`0009_local_probe_owner_role.py`) used to reassign two specific tables to the
app role directly - a workaround from before this two-role split existed. That
now conflicts with the model above (the owner role isn't a member of the app
role, so it can't hand off ownership) and is redundant besides, since the
default-privilege grants already cover every table. Both migrations were
turned into no-ops rather than deleted, to keep the migration history intact.

### Testing the Boundary

```sql
-- Connect as the app role
psql -U family_app -d family_app

-- These succeed (DML only):
SELECT * FROM households_household;
INSERT INTO household_task (household_id, ...) VALUES (...);

-- These fail (no DDL permission):
ALTER TABLE household_task DISABLE ROW LEVEL SECURITY;  -- ERROR: must be owner of table household_task
CREATE TABLE new_table (id int);                        -- ERROR: permission denied for schema public
```

This exact sequence was rehearsed against a disposable local database as part
of implementing this design: fresh `init-postgres.sh`-equivalent setup,
`migrate` via the superuser+`SET ROLE` DSN, then both boundary checks above
run as the app role and produced precisely these errors.

## Future Hardening

1. **Audit Tables**: Add PostgreSQL audit extension (`pgaudit`) to log all queries
2. **Secrets Management**: Use AWS Secrets Manager or HashiCorp Vault for password rotation
3. **Connection Pooling**: Use PgBouncer with per-connection auth to enforce app-role-only connections

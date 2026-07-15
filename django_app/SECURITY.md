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
from finance.code_utils import verify_invite_code
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

- `ops/init-postgres.sh` creates both roles and sets default privileges
- `ops/restore.sh` restores backup and reassigns ownership (owner role), then grants DML to app role

### Testing the Boundary

```sql
-- Connect as app role
psql -U family_app -d family_app

-- These will succeed:
SELECT * FROM users;
INSERT INTO users (...) VALUES (...);

-- These will fail (no DDL permission):
ALTER TABLE users DISABLE ROW LEVEL SECURITY;  -- ERROR: permission denied
CREATE TABLE new_table (...);                  -- ERROR: permission denied
```

## Future Hardening

1. **Audit Tables**: Add PostgreSQL audit extension (`pgaudit`) to log all queries
2. **Secrets Management**: Use AWS Secrets Manager or HashiCorp Vault for password rotation
3. **Connection Pooling**: Use PgBouncer with per-connection auth to enforce app-role-only connections

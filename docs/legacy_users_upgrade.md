# Legacy upgrade to users.CustomUser

Use this only for existing databases created before `AUTH_USER_MODEL = "users.CustomUser"`.

## Why

Legacy DBs may fail with `InconsistentMigrationHistory` because `admin.0001_initial`
is already applied but now depends on `users.0001_initial`.

This upgrade keeps authentication legacy-compatible:
- users continue to log in with their existing `username`
- no placeholder email is required for login

## Steps

1. Backup your database.
2. Restore the backup to a clone/staging environment and run a smoke test there first.
3. Bootstrap migration state and missing users tables.
4. Copy users 1:1 from `auth_user` to `users_customuser`.
5. Run normal migrations.
6. Verify there are no remaining foreign keys pointing to `auth_user`.

### Commands

```powershell
uv run python manage.py check
uv run python manage.py bootstrap_users_migration
uv run python manage.py migrate users 0002
uv run python manage.py migrate
uv run python manage.py verify_legacy_user_fks
```

### Validate login behavior

```powershell
uv run python manage.py shell
```

```python
from django.contrib.auth import authenticate

# Replace with a real legacy username/password
user = authenticate(username="legacy_username", password="legacy_password")
print(bool(user))
```

## Notes

- `bootstrap_users_migration` is idempotent.
- Fresh installs should **not** use this command.
- Legacy users should keep signing in with their previous username.
- If bootstrap detects a partially modified users schema, it aborts with `CommandError`.

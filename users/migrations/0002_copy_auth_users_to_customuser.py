import secrets
from datetime import datetime
from datetime import timezone as dt_timezone

from django.db import migrations


def copy_users_forward(apps, schema_editor):
    def _as_utc_aware(value):
        if value is None or not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=dt_timezone.utc)
        return value.astimezone(dt_timezone.utc)

    connection = schema_editor.connection
    db_alias = connection.alias
    table_names = set(connection.introspection.table_names())

    # Fresh installs with AUTH_USER_MODEL=users.CustomUser do not create auth_user.
    if "auth_user" not in table_names:
        return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, username, email, password,
                   is_staff, is_active, is_superuser,
                   date_joined, last_login,
                   first_name, last_name
            FROM auth_user
            ORDER BY id
            """
        )
        auth_users = cursor.fetchall()

        user_groups = []
        if "auth_user_groups" in table_names:
            cursor.execute("SELECT user_id, group_id FROM auth_user_groups")
            user_groups = cursor.fetchall()

        user_permissions = []
        if "auth_user_user_permissions" in table_names:
            cursor.execute(
                "SELECT user_id, permission_id FROM auth_user_user_permissions"
            )
            user_permissions = cursor.fetchall()

    group_map = {}
    for user_id, group_id in user_groups:
        group_map.setdefault(user_id, []).append(group_id)

    permission_map = {}
    for user_id, permission_id in user_permissions:
        permission_map.setdefault(user_id, []).append(permission_id)

    CustomUser = apps.get_model("users", "CustomUser")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    for row in auth_users:
        (
            user_id,
            username,
            email,
            password,
            is_staff,
            is_active,
            is_superuser,
            date_joined,
            last_login,
            first_name,
            last_name,
        ) = row

        normalized_email = (email or "").strip()
        legacy_email = normalized_email or f"{username}@genaigrader.local"

        date_joined = _as_utc_aware(date_joined)
        last_login = _as_utc_aware(last_login)
        custom_user, _ = CustomUser.objects.using(db_alias).get_or_create(
            id=user_id,
            defaults={
                "username": username,
                "email": legacy_email,
                "password": password,
                "is_staff": is_staff,
                "is_active": is_active,
                "is_superuser": is_superuser,
                "date_joined": date_joined,
                "last_login": last_login,
                "first_name": first_name or "",
                "last_name": last_name or "",
                "api_token": secrets.token_urlsafe(32),
            },
        )

        group_ids = group_map.get(user_id, [])
        if group_ids:
            groups = Group.objects.using(db_alias).filter(id__in=group_ids)
            custom_user.groups.set(groups)

        permission_ids = permission_map.get(user_id, [])
        if permission_ids:
            permissions = Permission.objects.using(db_alias).filter(
                id__in=permission_ids
            )
            custom_user.user_permissions.set(permissions)

    if connection.vendor == "postgresql":
        table_name = CustomUser._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT MAX(id) FROM {table_name}")
            max_id = cursor.fetchone()[0]
            if max_id is not None:
                cursor.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), %s, true)",
                    [max_id],
                )


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(copy_users_forward, migrations.RunPython.noop),
    ]

import re

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from users.models import CustomUser, ExternalIdentity


class Command(BaseCommand):
    help = (
        "Bootstrap users.0001_initial for legacy databases to avoid "
        "InconsistentMigrationHistory after switching AUTH_USER_MODEL."
    )

    def handle(self, *args, **options):
        self._ensure_legacy_user_emails()

        recorder = MigrationRecorder(connection)
        recorder.ensure_schema()

        applied = set(recorder.migration_qs.values_list("app", "name"))
        if ("users", "0001_initial") in applied:
            self.stdout.write(
                self.style.SUCCESS("users.0001_initial is already applied.")
            )
            return

        existing_tables = set(connection.introspection.table_names())
        with connection.schema_editor() as schema_editor:
            self._ensure_custom_user_tables(schema_editor, existing_tables)
            self._ensure_table(schema_editor, ExternalIdentity, existing_tables)

        recorder.record_applied("users", "0001_initial")
        self.stdout.write(
            self.style.SUCCESS(
                "Marked users.0001_initial as applied. Now run: "
                "uv run python manage.py migrate users 0002 && uv run python manage.py migrate"
            )
        )

    def _ensure_legacy_user_emails(self) -> None:
        table_names = set(connection.introspection.table_names())
        if "auth_user" not in table_names:
            return

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username
                FROM auth_user
                WHERE email IS NULL OR TRIM(email) = ''
                ORDER BY id
                """
            )
            missing_email_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT LOWER(TRIM(email))
                FROM auth_user
                WHERE email IS NOT NULL AND TRIM(email) <> ''
                """
            )
            used_emails = {row[0] for row in cursor.fetchall() if row[0]}

        if not missing_email_rows:
            return

        updates = []
        for user_id, username in missing_email_rows:
            username_seed = re.sub(
                r"[^a-z0-9._-]", "", (username or "").strip().lower()
            )
            if not username_seed:
                username_seed = "user"

            candidate = f"{username_seed}@genaigrader.local"
            if candidate in used_emails:
                candidate = f"legacy{user_id}@genaigrader.local"

            suffix = 1
            while candidate in used_emails:
                candidate = f"legacy{user_id}.{suffix}@genaigrader.local"
                suffix += 1

            used_emails.add(candidate)
            updates.append((candidate, user_id))

        with connection.cursor() as cursor:
            cursor.executemany("UPDATE auth_user SET email = %s WHERE id = %s", updates)

        self.stdout.write(
            self.style.WARNING(
                f"Assigned generated emails to {len(updates)} legacy user(s) in auth_user."
            )
        )

    def _ensure_custom_user_tables(self, schema_editor, existing_tables) -> None:
        user_table = CustomUser._meta.db_table
        group_through = CustomUser.groups.through._meta.db_table
        permission_through = CustomUser.user_permissions.through._meta.db_table
        m2m_tables = {group_through, permission_through}

        if user_table in existing_tables:
            self._ensure_table(schema_editor, CustomUser, existing_tables)
            self._ensure_m2m_tables(schema_editor, existing_tables)
            return

        preexisting_m2m_tables = sorted(m2m_tables.intersection(existing_tables))
        if preexisting_m2m_tables:
            raise CommandError(
                "Legacy bootstrap aborted: "
                f"found existing M2M table(s) {preexisting_m2m_tables} but '{user_table}' "
                "does not exist. This indicates a partial users schema. "
                "Repair the schema on a clone and retry."
            )

        # create_model() automatically creates M2M through tables, so we only create CustomUser.
        schema_editor.create_model(CustomUser)
        existing_tables.update({user_table, *m2m_tables})
        self.stdout.write(
            self.style.WARNING(f"Created table {user_table} for legacy bootstrap.")
        )

    def _ensure_m2m_tables(self, schema_editor, existing_tables) -> None:
        through_models = (
            CustomUser.groups.through,
            CustomUser.user_permissions.through,
        )

        for through_model in through_models:
            table_name = through_model._meta.db_table
            if table_name in existing_tables:
                continue
            schema_editor.create_model(through_model)
            existing_tables.add(table_name)
            self.stdout.write(
                self.style.WARNING(
                    f"Created missing M2M table {table_name} for legacy bootstrap."
                )
            )

    def _ensure_table(self, schema_editor, model, existing_tables):
        conn = schema_editor.connection
        table_name = model._meta.db_table
        expected_columns = {field.column for field in model._meta.local_fields}

        if table_name in existing_tables:
            with conn.cursor() as cursor:
                current_columns = {
                    column.name
                    for column in conn.introspection.get_table_description(
                        cursor, table_name
                    )
                }

            missing_columns = sorted(expected_columns - current_columns)
            if missing_columns:
                raise CommandError(
                    "Legacy bootstrap aborted: "
                    f"table '{table_name}' exists but is missing columns {missing_columns}. "
                    "Run backup + smoke test on a clone and repair schema before retrying."
                )
            return

        schema_editor.create_model(model)
        existing_tables.add(table_name)
        self.stdout.write(
            self.style.WARNING(f"Created table {table_name} for legacy bootstrap.")
        )

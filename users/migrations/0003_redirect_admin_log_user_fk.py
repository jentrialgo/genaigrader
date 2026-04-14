import re

from django.db import migrations


def _legacy_auth_fk_tables(connection) -> dict[str, list[tuple[str, list[str], str]]]:
    legacy_by_table: dict[str, list[tuple[str, list[str], str]]] = {}

    with connection.cursor() as cursor:
        for table_name in connection.introspection.table_names():
            constraints = connection.introspection.get_constraints(cursor, table_name)
            for constraint_name, data in constraints.items():
                foreign_key = data.get("foreign_key")
                if not foreign_key or foreign_key[0] != "auth_user":
                    continue

                columns = list(data.get("columns") or [])
                if not columns:
                    continue

                referenced_column = foreign_key[1] or "id"
                legacy_by_table.setdefault(table_name, []).append(
                    (constraint_name, columns, referenced_column)
                )

    return legacy_by_table


def _postgres_redirect_legacy_fks(connection) -> None:
    quote = connection.ops.quote_name
    legacy_by_table = _legacy_auth_fk_tables(connection)

    with connection.cursor() as cursor:
        for table_name, fk_items in legacy_by_table.items():
            table_sql = quote(table_name)
            for constraint_name, columns, referenced_column in fk_items:
                cols_sql = ", ".join(quote(column) for column in columns)
                constraint_sql = quote(constraint_name)
                ref_col_sql = quote(referenced_column)

                cursor.execute(
                    f"ALTER TABLE {table_sql} DROP CONSTRAINT IF EXISTS {constraint_sql}"
                )
                cursor.execute(
                    f"ALTER TABLE {table_sql} "
                    f"ADD CONSTRAINT {constraint_sql} "
                    f"FOREIGN KEY ({cols_sql}) REFERENCES {quote('users_customuser')} ({ref_col_sql}) "
                    "DEFERRABLE INITIALLY DEFERRED"
                )


def _sqlite_quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sqlite_rebuild_table_fk_to_custom_user(connection, table_name: str) -> None:
    quoted_table = _sqlite_quote(table_name)
    tmp_table = f"{table_name}__tmp_users_customuser_fk"
    quoted_tmp_table = _sqlite_quote(tmp_table)

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = %s",
            [table_name],
        )
        row = cursor.fetchone()
        if not row or not row[0]:
            return

        create_sql = row[0]
        if "auth_user" not in create_sql.lower():
            return

        updated_sql = re.sub(
            r"REFERENCES\s+[\"'`]?auth_user[\"'`]?(\s*\()",
            r'REFERENCES "users_customuser"\1',
            create_sql,
            flags=re.IGNORECASE,
        )
        updated_sql = re.sub(
            rf'CREATE\s+TABLE\s+"{re.escape(table_name)}"',
            f"CREATE TABLE {quoted_tmp_table}",
            updated_sql,
            count=1,
            flags=re.IGNORECASE,
        )
        updated_sql = re.sub(
            rf"CREATE\s+TABLE\s+{re.escape(table_name)}",
            f"CREATE TABLE {quoted_tmp_table}",
            updated_sql,
            count=1,
            flags=re.IGNORECASE,
        )

        cursor.execute(f"PRAGMA table_info({quoted_table})")
        columns = [row_data[1] for row_data in cursor.fetchall()]
        if not columns:
            return

        quoted_columns = ", ".join(_sqlite_quote(column) for column in columns)

        cursor.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = %s AND sql IS NOT NULL",
            [table_name],
        )
        index_sqls = [index_row[0] for index_row in cursor.fetchall() if index_row[0]]

        cursor.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'trigger' AND tbl_name = %s AND sql IS NOT NULL",
            [table_name],
        )
        trigger_sqls = [
            trigger_row[0] for trigger_row in cursor.fetchall() if trigger_row[0]
        ]

        cursor.execute(f"DROP TABLE IF EXISTS {quoted_tmp_table}")
        cursor.execute(updated_sql)
        cursor.execute(
            f"INSERT INTO {quoted_tmp_table} ({quoted_columns}) "
            f"SELECT {quoted_columns} FROM {quoted_table}"
        )
        cursor.execute(f"DROP TABLE {quoted_table}")
        cursor.execute(f"ALTER TABLE {quoted_tmp_table} RENAME TO {quoted_table}")

        for index_sql in index_sqls:
            cursor.execute(index_sql)

        for trigger_sql in trigger_sqls:
            cursor.execute(trigger_sql)


def _sqlite_redirect_legacy_fks(connection) -> None:
    legacy_by_table = _legacy_auth_fk_tables(connection)
    if not legacy_by_table:
        return

    with connection.cursor() as cursor:
        cursor.execute("PRAGMA foreign_keys")
        row = cursor.fetchone()
        previous_state = bool(row and row[0])
        cursor.execute("PRAGMA foreign_keys=OFF")

    try:
        for table_name in sorted(legacy_by_table.keys()):
            _sqlite_rebuild_table_fk_to_custom_user(connection, table_name)
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"PRAGMA foreign_keys={'ON' if previous_state else 'OFF'}")


def redirect_legacy_auth_user_fks(apps, schema_editor) -> None:
    connection = schema_editor.connection
    table_names = set(connection.introspection.table_names())

    if "users_customuser" not in table_names:
        return

    if connection.vendor == "postgresql":
        _postgres_redirect_legacy_fks(connection)
        return

    if connection.vendor == "sqlite":
        _sqlite_redirect_legacy_fks(connection)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("users", "0002_copy_auth_users_to_customuser"),
    ]

    operations = [
        migrations.RunPython(redirect_legacy_auth_user_fks, migrations.RunPython.noop),
    ]

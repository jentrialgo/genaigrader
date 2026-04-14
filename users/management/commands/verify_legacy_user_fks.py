from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = (
        "Fail if any database foreign key still points to auth_user after "
        "migrating to users.CustomUser."
    )

    def handle(self, *args, **options):
        legacy_refs: list[str] = []

        with connection.cursor() as cursor:
            for table_name in connection.introspection.table_names():
                constraints = connection.introspection.get_constraints(
                    cursor, table_name
                )
                for data in constraints.values():
                    foreign_key = data.get("foreign_key")
                    if not foreign_key or foreign_key[0] != "auth_user":
                        continue

                    columns = ", ".join(data.get("columns") or []) or "<unknown>"
                    legacy_refs.append(f"{table_name}({columns})")

        refs = sorted(set(legacy_refs))
        if refs:
            raise CommandError(
                "Legacy FK references to auth_user are still present: "
                + ", ".join(refs)
            )

        self.stdout.write(
            self.style.SUCCESS(
                "No legacy foreign keys pointing to auth_user were found."
            )
        )

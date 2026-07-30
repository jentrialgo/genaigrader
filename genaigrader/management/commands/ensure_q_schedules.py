"""Ensure the required django-q2 Schedule entries exist.

This command is idempotent: running it multiple times will not create
duplicate schedules.
"""

import logging

from django.core.management.base import BaseCommand
from django_q.models import Schedule

logger = logging.getLogger(__name__)

SCHEDULE_NAME = "cleanup-stale-tasks"
SCHEDULE_FUNC = "genaigrader.tasks.cleanup_stale_tasks_task"


class Command(BaseCommand):
    help = "Register or update required django-q2 schedules (idempotent)."

    def handle(self, **options):
        schedule, created = Schedule.objects.update_or_create(
            name=SCHEDULE_NAME,
            defaults={
                "func": SCHEDULE_FUNC,
                "schedule_type": Schedule.MINUTES,
                "minutes": 15,
                "repeats": -1,
            },
        )
        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} schedule '{SCHEDULE_NAME}' "
                f"(func={SCHEDULE_FUNC}, every {schedule.minutes} min)"
            )
        )

from django.core.management import call_command
from django.test import TestCase
from django_q.models import Schedule


class EnsureQSchedulesTest(TestCase):
    """Tests for the ensure_q_schedules management command."""

    def test_creates_schedule(self):
        self.assertEqual(Schedule.objects.count(), 0)

        call_command("ensure_q_schedules")

        self.assertEqual(Schedule.objects.count(), 1)
        schedule = Schedule.objects.first()
        self.assertEqual(schedule.name, "cleanup-stale-tasks")
        self.assertEqual(schedule.func, "genaigrader.tasks.cleanup_stale_tasks_task")
        self.assertEqual(schedule.schedule_type, Schedule.MINUTES)
        self.assertEqual(schedule.minutes, 15)
        self.assertEqual(schedule.repeats, -1)

    def test_idempotent(self):
        call_command("ensure_q_schedules")
        call_command("ensure_q_schedules")

        self.assertEqual(Schedule.objects.count(), 1)

    def test_updates_existing(self):
        Schedule.objects.create(
            name="cleanup-stale-tasks",
            func="genaigrader.tasks.cleanup_stale_tasks_task",
            schedule_type=Schedule.MINUTES,
            minutes=30,
            repeats=-1,
        )

        call_command("ensure_q_schedules")

        schedule = Schedule.objects.get(name="cleanup-stale-tasks")
        self.assertEqual(schedule.minutes, 15)

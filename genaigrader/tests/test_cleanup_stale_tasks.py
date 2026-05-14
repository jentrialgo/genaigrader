from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from django_q.models import OrmQ, Task
from django_q.signing import SignedPackage


def _make_ormq_payload(func_path, args=None, kwargs=None, task_id="a" * 32):
    """Build a signed payload dict mimicking django-q2's internal format."""
    return SignedPackage.dumps(
        {
            "id": task_id,
            "func": func_path,
            "args": args or (),
            "kwargs": kwargs or {},
            "name": func_path.rsplit(".", 1)[-1],
        }
    )


class CleanupStaleTasksTest(TestCase):
    """Tests for the cleanup_stale_tasks management command."""

    def _call_command(self, **options):
        out = StringIO()
        call_command("cleanup_stale_tasks", stdout=out, **options)
        return out.getvalue()

    def test_healthy_queued_task_not_purged(self):
        """A queued task whose evaluation still exists must not be deleted."""
        OrmQ.objects.create(
            key="test-key-1",
            payload=_make_ormq_payload(
                "genaigrader.tasks.evaluate_question_task", args=[999]
            ),
        )

        with patch(
            "genaigrader.management.commands.cleanup_stale_tasks.Evaluation"
        ) as MockEval:
            MockEval.objects.filter.return_value.exists.return_value = True
            output = self._call_command()

        self.assertTrue(OrmQ.objects.filter(key="test-key-1").exists())
        self.assertIn("No orphaned OrmQ entries found", output)

    def test_orphaned_queued_task_purged(self):
        """A queued task whose evaluation no longer exists should be deleted."""
        OrmQ.objects.create(
            key="test-key-2",
            payload=_make_ormq_payload(
                "genaigrader.tasks.evaluate_question_task", args=[999]
            ),
        )

        with patch(
            "genaigrader.management.commands.cleanup_stale_tasks.Evaluation"
        ) as MockEval:
            MockEval.objects.filter.return_value.exists.return_value = False
            output = self._call_command()

        self.assertFalse(OrmQ.objects.filter(key="test-key-2").exists())
        self.assertIn("Removed 1 orphaned OrmQ entries", output)

    def test_non_evaluation_task_not_purged(self):
        """A queued task that is not an evaluation task must not be deleted."""
        OrmQ.objects.create(
            key="test-key-3",
            payload=_make_ormq_payload(
                "genaigrader.tasks.download_model_task", args=["llama3.2:1b"]
            ),
        )

        output = self._call_command()

        self.assertTrue(OrmQ.objects.filter(key="test-key-3").exists())
        self.assertIn("No orphaned OrmQ entries found", output)

    def test_old_task_with_stopped_deleted(self):
        """Task records older than --days with a stopped timestamp are deleted."""
        old_time = timezone.now() - timedelta(days=60)
        Task.objects.create(
            id="b" * 32,
            name="old-task",
            func="genaigrader.tasks.evaluate_question_task",
            started=old_time,
            stopped=old_time + timedelta(seconds=10),
            success=True,
        )

        output = self._call_command(days=30)

        self.assertEqual(Task.objects.count(), 0)
        self.assertIn("Removed 1 Task records", output)

    def test_recent_task_not_deleted(self):
        """Recent Task records must not be deleted."""
        recent_time = timezone.now() - timedelta(days=5)
        Task.objects.create(
            id="c" * 32,
            name="recent-task",
            func="genaigrader.tasks.evaluate_question_task",
            started=recent_time,
            stopped=recent_time + timedelta(seconds=10),
            success=True,
        )

        output = self._call_command(days=30)

        self.assertEqual(Task.objects.count(), 1)
        self.assertIn("Removed 0 Task records", output)

    def test_dry_run_does_not_delete(self):
        """With --dry-run, no records are actually deleted."""
        OrmQ.objects.create(
            key="test-key-dry",
            payload=_make_ormq_payload(
                "genaigrader.tasks.evaluate_question_task", args=[999]
            ),
        )
        old_time = timezone.now() - timedelta(days=60)
        Task.objects.create(
            id="d" * 32,
            name="old-task-dry",
            func="genaigrader.tasks.evaluate_question_task",
            started=old_time,
            stopped=old_time + timedelta(seconds=10),
            success=True,
        )

        with patch(
            "genaigrader.management.commands.cleanup_stale_tasks.Evaluation"
        ) as MockEval:
            MockEval.objects.filter.return_value.exists.return_value = False
            output = self._call_command(dry_run=True)

        self.assertTrue(OrmQ.objects.filter(key="test-key-dry").exists())
        self.assertEqual(Task.objects.count(), 1)
        self.assertIn("dry run", output)

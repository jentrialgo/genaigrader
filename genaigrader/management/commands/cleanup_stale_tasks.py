import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_q.models import OrmQ, Task

from genaigrader.models import Evaluation
from genaigrader.services.stale_evaluation_service import reap_stale_evaluations

logger = logging.getLogger(__name__)

EVALUATION_TASK_FUNC = "genaigrader.tasks.evaluate_question_task"


class Command(BaseCommand):
    help = (
        "Remove stale queued tasks (OrmQ), delete Task records older than N days, "
        "and reap stale Evaluations stuck in pending/running."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Delete Task records older than this many days (default: 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting.",
        )
        parser.add_argument(
            "--no-reap",
            action="store_true",
            help="Skip reaping stale Evaluations (only clean OrmQ and Task records).",
        )

    def handle(self, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        no_reap = options["no_reap"]

        cutoff = timezone.now() - timedelta(days=days)

        # ── Clean orphaned OrmQ entries ──────────────────────────────────
        orphan_pks = []
        for entry in OrmQ.objects.iterator():
            if entry.task_id() is None:
                orphan_pks.append(entry.pk)
                continue
            try:
                func_name = entry.func()
                if not func_name:
                    orphan_pks.append(entry.pk)
                    continue
                if func_name == EVALUATION_TASK_FUNC:
                    eval_id = entry.args()[0] if entry.args() else None
                    if eval_id is not None:
                        if not Evaluation.objects.filter(id=eval_id).exists():
                            orphan_pks.append(entry.pk)
            except (AttributeError, TypeError, ValueError, IndexError):
                orphan_pks.append(entry.pk)
            except Exception as exc:
                logger.warning(
                    "Unexpected error inspecting OrmQ entry %s: %s", entry.pk, exc
                )

        if orphan_pks:
            count_orm = len(orphan_pks)
            if not dry_run:
                OrmQ.objects.filter(pk__in=orphan_pks).delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Removed {count_orm} orphaned OrmQ entries"
                    + (" (dry run)" if dry_run else "")
                )
            )
        else:
            self.stdout.write("No orphaned OrmQ entries found.")

        # ── Clean old Task records ───────────────────────────────────────
        old_tasks = Task.objects.filter(stopped__lt=cutoff)
        count_task = old_tasks.count()
        if not dry_run:
            old_tasks.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Removed {count_task} Task records older than {days} days"
                + (" (dry run)" if dry_run else "")
            )
        )

        # ── Reap stale Evaluations ───────────────────────────────────────
        if not no_reap:
            if dry_run:
                self.stdout.write("Skipping stale Evaluation reap in dry-run mode.")
            else:
                result = reap_stale_evaluations()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Reaped {result['reaped']} stale Evaluation(s) "
                        f"(grace={result['grace_minutes']} min)"
                    )
                )

"""Detect and reap Evaluations that are stuck in pending/running.

An Evaluation is considered stale when ALL of these hold:

1. Its status is ``pending`` or ``running``.
2. Its ``ev_date`` is older than the configured grace period.
3. There are NO ``OrmQ`` entries (queued or locked/in-flight) for the
   ``evaluate_question_task`` of this evaluation.
4. The number of ``QuestionEvaluation`` rows is lower than
   ``total_questions`` (incomplete).

A stale Evaluation is transitioned to ``failed`` with a human-readable
reason so the UI no longer shows it as eternally running.
"""

import logging
from datetime import timedelta
from typing import Optional, Set

from django.conf import settings
from django.utils import timezone
from django_q.models import OrmQ

from genaigrader.models import Evaluation, QuestionEvaluation

logger = logging.getLogger(__name__)

EVALUATION_TASK_FUNC = "genaigrader.tasks.evaluate_question_task"

_DEFAULT_GRACE_MINUTES = 30


def _get_grace_minutes() -> int:
    """Return the configured grace period in minutes."""
    return getattr(settings, "STALE_EVALUATION_GRACE_MINUTES", _DEFAULT_GRACE_MINUTES)


def _get_queued_evaluation_ids() -> Set[int]:
    """Return the set of evaluation IDs that still have tasks in OrmQ.

    This covers both queued (lock expired) and locked (in-flight) tasks.
    """
    eval_ids: Set[int] = set()
    for entry in OrmQ.objects.iterator():
        try:
            if entry.func() != EVALUATION_TASK_FUNC:
                continue
            args = entry.args()
            if args and isinstance(args[0], int):
                eval_ids.add(args[0])
        except Exception:
            logger.warning(
                "Could not inspect OrmQ entry %s for stale detection",
                entry.pk,
                exc_info=True,
            )
    return eval_ids


def reap_stale_evaluations(grace_minutes: Optional[int] = None) -> dict:
    """Mark stale Evaluations as failed.

    Parameters
    ----------
    grace_minutes : int, optional
        Override the configured grace period. If ``None``, the setting
        ``STALE_EVALUATION_GRACE_MINUTES`` (default 30) is used.

    Returns
    -------
    dict
        Summary with keys:
        - ``grace_minutes`` (int)
        - ``reaped`` (int): number of evaluations marked failed
        - ``reaped_ids`` (list[int])
    """
    if grace_minutes is None:
        grace_minutes = _get_grace_minutes()

    cutoff = timezone.now() - timedelta(minutes=grace_minutes)
    queued_eval_ids = _get_queued_evaluation_ids()

    candidates = Evaluation.objects.filter(
        status__in=("pending", "running"),
        ev_date__lt=cutoff,
    )

    reaped_ids = []
    for evaluation in candidates:
        if evaluation.id in queued_eval_ids:
            continue

        completed = QuestionEvaluation.objects.filter(evaluation=evaluation).count()

        if completed >= evaluation.total_questions:
            # All questions done but status never moved to completed.
            # This is a rare race; fix it instead of failing.
            from genaigrader.services.stream_service import compute_evaluation_summary

            grade, total_time = compute_evaluation_summary(evaluation)
            evaluation.grade = grade
            evaluation.time = total_time
            evaluation.status = "completed"
            evaluation.save()
            logger.info(
                "Fixed stale evaluation %s: had all %s/%s answers, marked completed",
                evaluation.id,
                completed,
                evaluation.total_questions,
            )
            continue

        reason = (
            f"Stale: no remaining queue tasks and incomplete "
            f"({completed}/{evaluation.total_questions} questions done)"
        )
        Evaluation.objects.filter(
            id=evaluation.id, status__in=("pending", "running")
        ).update(
            status="failed",
            failed_reason=reason[:500],
        )
        reaped_ids.append(evaluation.id)
        logger.info(
            "Reaped stale evaluation %s (status=%s, completed=%s/%s)",
            evaluation.id,
            evaluation.status,
            completed,
            evaluation.total_questions,
        )

    result = {
        "grace_minutes": grace_minutes,
        "reaped": len(reaped_ids),
        "reaped_ids": reaped_ids,
    }
    logger.info(
        "Stale evaluation reaper finished: %s reaped (grace=%s min)",
        result["reaped"],
        grace_minutes,
    )
    return result

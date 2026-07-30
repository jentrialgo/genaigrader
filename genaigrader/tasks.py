"""
Background task definitions for django-q2.

These functions are the entry points for async task execution.
They wrap the service layer and are designed to be picklable
for serialization by the django-q2 broker.
"""

import logging
from typing import Dict, List

from django_q.tasks import async_task

from genaigrader.models import Evaluation
from genaigrader.services.model_service import pull_model
from genaigrader.services.stream_service import evaluate_single_question

logger = logging.getLogger(__name__)

EVALUATION_TASK_TIMEOUT = 3600


def batch_orchestrator_task(
    evaluations_meta: List[Dict],
    exam_questions_map: Dict[int, List[int]],
    user_prompt: str = "",
) -> dict:
    """Background orchestrator: enqueue per-question tasks for a batch of stubs.

    The stubs are already created by the view; this task only enqueues the
    individual ``evaluate_question_task`` workers so the HTTP response returns
    quickly instead of blocking for the entire enqueue loop.

    Parameters
    ----------
    evaluations_meta : list[dict]
        Each dict has ``id`` (eval stub PK), ``exam_id``, ``model_id``, etc.
    exam_questions_map : dict[int, list[int]]
        Mapping of exam_id → list of question IDs.
    user_prompt : str
        Optional custom prompt text.
    """
    logger.info(
        "Orchestrator started: %s evaluations across %s exams",
        len(evaluations_meta),
        len(exam_questions_map),
    )
    eval_ids = [m["id"] for m in evaluations_meta]
    task_count = 0
    try:
        for meta in evaluations_meta:
            eval_id = meta["id"]
            exam_id = meta["exam_id"]
            for question_id in exam_questions_map.get(exam_id, []):
                async_task(
                    evaluate_question_task,
                    eval_id,
                    question_id,
                    user_prompt,
                    group=f"eval:{eval_id}",
                    timeout=EVALUATION_TASK_TIMEOUT,
                )
                task_count += 1
    except Exception:
        logger.exception(
            "Orchestrator failed after %s tasks; marking remaining stubs as failed",
            task_count,
        )
        Evaluation.objects.filter(
            id__in=eval_ids, status__in=("pending", "running")
        ).update(
            status="failed",
            failed_reason="Batch orchestrator failure",
        )
        raise

    logger.info(
        "Orchestrator finished: %s question task(s) enqueued",
        task_count,
    )
    return {"status": "ok", "task_count": task_count}


def evaluate_question_task(evaluation_id, question_id, user_prompt=""):
    """
    Evaluate a single question as a background task.

    Parameters
    ----------
    evaluation_id : int
        ID of the parent Evaluation stub.
    question_id : int
        ID of the question to evaluate.
    user_prompt : str, optional
        Optional custom prompt text.

    Returns
    -------
    dict
        Result containing evaluation_id, question_id, response, is_correct, etc.
    """
    evaluation = Evaluation.objects.filter(id=evaluation_id).first()
    if not evaluation:
        logger.warning(
            "Evaluation %s no longer exists, discarding task for question %s.",
            evaluation_id,
            question_id,
        )
        return {
            "status": "discarded",
            "reason": "evaluation deleted",
            "evaluation_id": evaluation_id,
            "question_id": question_id,
        }

    if evaluation.status in ("completed", "failed"):
        logger.warning(
            "Evaluation %s already terminal (%s), discarding task for question %s.",
            evaluation_id,
            evaluation.status,
            question_id,
        )
        return {
            "status": "discarded",
            "reason": f"evaluation already {evaluation.status}",
            "evaluation_id": evaluation_id,
            "question_id": question_id,
        }

    logger.info(
        "Starting question evaluation task: eval=%s question=%s",
        evaluation_id,
        question_id,
    )
    try:
        result = evaluate_single_question(evaluation_id, question_id, user_prompt)
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        logger.exception(
            "Task-level failure: eval=%s question=%s error_type=%s",
            evaluation_id,
            question_id,
            type(exc).__name__,
        )
        Evaluation.objects.filter(
            id=evaluation_id, status__in=("pending", "running")
        ).update(
            status="failed",
            failed_question_id=question_id,
            failed_reason=f"Task error ({type(exc).__name__}): {exc}"[:500],
        )
        raise
    logger.info(
        "Completed question evaluation task: eval=%s question=%s complete=%s",
        evaluation_id,
        question_id,
        result.get("evaluation_complete"),
    )
    return result


def download_model_task(model_name):
    """
    Download a model from Ollama as a background task.

    Parameters
    ----------
    model_name : str
        Name of the model to download.

    Returns
    -------
    dict
        Result containing model_id, model name, and status.
    """
    logger.info("Starting model download task: model=%s", model_name)
    result = pull_model(model_name)
    logger.info(
        "Completed model download task: model=%s model_id=%s",
        model_name,
        result.get("model_id"),
    )
    return result


def evaluate_exam_task(*args, **kwargs):
    """
    Backward-compatibility wrapper for stale tasks referencing an old task name.

    These tasks are obsolete and will be discarded gracefully.
    """
    logger.warning(
        "Discarding stale evaluate_exam_task: args=%s kwargs=%s", args, kwargs
    )
    return {"status": "discarded", "reason": "obsolete task name"}


def cleanup_stale_tasks_task(days=3):  # purge every 72h
    """
    Scheduled task: clean orphaned OrmQ entries, old Task records,
    and reap stale Evaluations stuck in pending/running.

    Parameters
    ----------
    days : int
        Delete Task records older than this many days.

    Returns
    -------
    dict
        Summary of what was cleaned and reaped.
    """
    from django.core.management import call_command

    logger.info("Running scheduled cleanup: days=%s", days)
    call_command("cleanup_stale_tasks", days=days)
    logger.info("Scheduled cleanup finished: days=%s", days)
    return {"status": "ok", "days": days}

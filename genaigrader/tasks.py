"""
Background task definitions for django-q2.

These functions are the entry points for async task execution.
They wrap the service layer and are designed to be picklable
for serialization by the django-q2 broker.
"""

import logging

from genaigrader.models import Evaluation
from genaigrader.services.model_service import pull_model
from genaigrader.services.stream_service import evaluate_single_question

logger = logging.getLogger(__name__)

EVALUATION_TASK_TIMEOUT = 3600


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

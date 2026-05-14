import logging
import time
from typing import Optional, Tuple

import ollama
import openai
from django.db import DatabaseError, transaction
from django.utils import timezone

from genaigrader.llm_api import LlmApi
from genaigrader.models import (
    Evaluation,
    Exam,
    Model,
    Question,
    QuestionEvaluation,
    QuestionOption,
)
from genaigrader.services.llm_service import generate_prompt
from genaigrader.services.ollama_version_service import get_evaluation_ollama_version

logger = logging.getLogger(__name__)


def create_evaluation_stub(
    exam_id: int,
    model_id: int,
    user_prompt: str = "",
    notes: Optional[str] = None,
) -> Evaluation:
    """
    Create an Evaluation stub in the database before enqueuing per-question tasks.

    Parameters
    ----------
    exam_id : int
        ID of the exam to evaluate.
    model_id : int
        ID of the model to use.
    user_prompt : str, optional
        Optional custom user prompt text.
    notes : str, optional
        Optional notes for the evaluation.

    Returns
    -------
    Evaluation
        The newly created Evaluation instance with status='pending'.

    Raises
    ------
    ValueError
        If the exam has no questions.
    """
    exam = Exam.objects.get(id=exam_id)
    model = Model.objects.get(id=model_id)

    total_questions = exam.question_set.count()
    if total_questions == 0:
        raise ValueError(f"Exam {exam} has no questions")

    prompt = (
        (f"{user_prompt}\n\n" if user_prompt else "")
        + "Te voy a pasar una pregunta de test y tienes que responderme con qué opción es la correcta. "
        "Sólo debes decirme la opción, por ejemplo 'a', absolutamente nada más.\n"
    )

    evaluation = Evaluation.objects.create(
        prompt=prompt,
        ev_date=timezone.now(),
        grade=0,
        time=0,
        model=model,
        exam=exam,
        ollama_version=get_evaluation_ollama_version(model),
        notes=notes,
        status="pending",
        total_questions=total_questions,
    )
    logger.info(
        "Created evaluation stub id=%s for exam=%s model=%s questions=%s",
        evaluation.id,
        exam_id,
        model_id,
        total_questions,
    )
    return evaluation


def compute_evaluation_summary(evaluation: Evaluation) -> Tuple[float, float]:
    """
    Compute the final grade and wall-clock time for a completed evaluation.

    Parameters
    ----------
    evaluation : Evaluation
        The evaluation to summarize.

    Returns
    -------
    tuple[float, float]
        (grade, time) where grade is 0-10 and time is seconds.
    """
    question_evals = QuestionEvaluation.objects.filter(evaluation=evaluation)
    total_questions = question_evals.count()

    if total_questions == 0:
        return 0.0, 0.0

    correct_count = question_evals.filter(is_correct=True).count()

    grade = round((correct_count / total_questions) * 10, 2)
    total_time = round(sum(qe.question_time for qe in question_evals), 2)

    return grade, total_time


def evaluate_single_question(
    evaluation_id: int,
    question_id: int,
    user_prompt: str = "",
) -> dict:
    """
    Evaluate a single question against the LLM and create a QuestionEvaluation.

    If this is the last question to complete the evaluation, the final grade
    and time are computed and the Evaluation is marked 'completed'.

    If the LLM call fails, the Evaluation is marked 'failed' with the
    question ID and error reason, and the original exception is re-raised.

    Parameters
    ----------
    evaluation_id : int
        ID of the parent Evaluation stub.
    question_id : int
        ID of the Question to evaluate.
    user_prompt : str, optional
        Optional custom prompt text.

    Returns
    -------
    dict
        Result dictionary with keys:
        - evaluation_id (int)
        - question_id (int)
        - response (str)
        - is_correct (bool)
        - question_time (float)
        - evaluation_complete (bool)
        - grade (float | None)
        - total_time (float | None)
    """
    evaluation = Evaluation.objects.select_related("exam", "model").get(
        id=evaluation_id
    )

    # Only transition from pending -> running. Do not overwrite terminal states.
    updated = Evaluation.objects.filter(id=evaluation_id, status="pending").update(
        status="running"
    )
    if updated == 0:
        logger.warning(
            "Evaluation %s is not pending; skipping status update.", evaluation_id
        )

    question = Question.objects.prefetch_related("questionoption_set").get(
        id=question_id
    )
    model = evaluation.model

    llm = LlmApi(model)
    prompt_data = generate_prompt(question, user_prompt)
    logger.info(
        "Evaluating question %s for evaluation %s",
        question_id,
        evaluation_id,
    )

    start_time = time.monotonic()
    try:
        llm_response_list = list(llm.generate_response(prompt_data["prompt"]))
    except (
        RuntimeError,
        ConnectionError,
        TimeoutError,
        ValueError,
        openai.OpenAIError,
        ollama.ResponseError,
    ) as exc:
        logger.exception(
            "LLM error on question %s evaluation %s: %s",
            question_id,
            evaluation_id,
            exc,
        )
        try:
            Evaluation.objects.filter(id=evaluation_id, status="running").update(
                status="failed",
                failed_question_id=question_id,
                failed_reason=str(exc),
            )
        except DatabaseError:
            logger.exception(
                "Failed to persist failure state for evaluation %s", evaluation_id
            )
        raise exc

    end_time = time.monotonic()
    question_time = end_time - start_time

    if not llm_response_list:
        response = ""
    else:
        first_token = llm_response_list[0].strip().lower()
        response = first_token[0] if first_token else ""

    is_correct = False
    selected_option = None
    if response:
        selected_option = QuestionOption.objects.filter(
            question=question, content__istartswith=response
        ).first()
        is_correct = response == question.correct_option.content.strip().lower()[0]

    # Atomically create/update the question evaluation and check for completion.
    evaluation_complete = False
    grade: Optional[float] = None
    total_time: Optional[float] = None

    with transaction.atomic():
        eval_locked = Evaluation.objects.select_for_update().get(id=evaluation_id)

        # Prevent duplicate evaluations for the same question.
        qe, created = QuestionEvaluation.objects.get_or_create(
            evaluation=eval_locked,
            question=question,
            defaults={
                "question_option": selected_option,
                "response_text": response,
                "is_correct": is_correct,
                "question_time": round(question_time, 2),
            },
        )
        if not created:
            logger.warning(
                "Duplicate question evaluation detected for eval=%s question=%s; keeping existing.",
                evaluation_id,
                question_id,
            )

        completed = QuestionEvaluation.objects.filter(evaluation=eval_locked).count()
        if completed >= eval_locked.total_questions and eval_locked.status not in (
            "completed",
            "failed",
        ):
            grade, total_time = compute_evaluation_summary(eval_locked)
            eval_locked.grade = grade
            eval_locked.time = total_time
            eval_locked.status = "completed"
            eval_locked.save()
            evaluation_complete = True
            logger.info(
                "Evaluation %s completed: grade=%s time=%ss",
                evaluation_id,
                grade,
                total_time,
            )

    return {
        "evaluation_id": evaluation_id,
        "question_id": question_id,
        "response": response,
        "is_correct": is_correct,
        "question_time": round(question_time, 2),
        "evaluation_complete": evaluation_complete,
        "grade": grade,
        "total_time": total_time,
    }

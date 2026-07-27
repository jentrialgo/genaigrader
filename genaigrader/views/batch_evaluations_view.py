import json
import logging
from typing import Dict, List

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django_q.tasks import async_task

from genaigrader.models import Course, Exam, Question
from genaigrader.services.get_models_service import get_models_for_user
from genaigrader.services.stream_service import create_evaluation_stub
from genaigrader.tasks import EVALUATION_TASK_TIMEOUT, evaluate_question_task

logger = logging.getLogger(__name__)


def _prefetch_exam_question_ids(
    exams_to_eval,
) -> Dict[int, List[int]]:
    """Return a mapping of exam_id → list of question IDs."""
    exam_questions = Question.objects.filter(exam__in=exams_to_eval).values_list(
        "exam_id", "id"
    )
    exam_to_questions: Dict[int, List[int]] = {}
    for exam_id, question_id in exam_questions:
        exam_to_questions.setdefault(exam_id, []).append(question_id)
    return exam_to_questions


def _parse_positive_int(value, default=1):
    """Parse a positive integer, falling back to *default* on invalid input."""
    try:
        parsed = int(value) if value is not None else default
        return parsed if parsed >= 1 else default
    except (ValueError, TypeError):
        return default


def handle_batch_evaluations_post(request, user, exams, models):
    logger.info("Batch evaluation POST received")
    if "application/json" in (request.content_type or ""):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(
                {"status": "error", "message": "Invalid JSON body"},
                status=400,
            )
        selected_exam_ids = data.get("exams[]", [])
        selected_model_ids = data.get("models[]", [])
        repetitions = _parse_positive_int(data.get("repetitions"), 1)
        user_prompt = data.get("user_prompt", "")
        notes = data.get("notes", "")
    else:
        selected_exam_ids = request.POST.getlist("exams[]")
        selected_model_ids = request.POST.getlist("models[]")
        repetitions = _parse_positive_int(request.POST.get("repetitions"), 1)
        user_prompt = request.POST.get("user_prompt", "")
        notes = request.POST.get("notes", "")

    logger.info(
        "selected_exam_ids=%s model_ids=%s repetitions=%s",
        selected_exam_ids,
        selected_model_ids,
        repetitions,
    )

    exams_to_eval = exams.filter(id__in=selected_exam_ids)
    models_to_eval = [m for m in models if str(m.id) in selected_model_ids]
    logger.info(
        "exams_to_eval=%s models_to_eval=%s",
        [e.id for e in exams_to_eval],
        [m.id for m in models_to_eval],
    )

    exam_ids = [e.id for e in exams_to_eval]
    model_ids = [m.id for m in models_to_eval]

    exam_questions_map = _prefetch_exam_question_ids(exams_to_eval)

    task_ids = []
    evaluation_ids = []
    evaluations_meta = []
    rep_counter = {}

    logger.info(
        "Enqueuing batch: %d model(s) x %d exam(s) x %d rep(s), ordered by model",
        len(model_ids),
        len(exam_ids),
        repetitions,
    )

    for model_id in model_ids:
        for exam_id in exam_ids:
            for rep in range(1, repetitions + 1):
                eval_stub = create_evaluation_stub(
                    exam_id, model_id, user_prompt, notes
                )
                evaluation_ids.append(eval_stub.id)
                key = (exam_id, model_id)
                if key not in rep_counter:
                    rep_counter[key] = 0
                rep_counter[key] += 1
                current_rep = rep_counter[key]
                evaluations_meta.append(
                    {
                        "id": eval_stub.id,
                        "exam_id": exam_id,
                        "model_id": model_id,
                        "repetition": current_rep,
                        "total_repetitions": repetitions,
                    }
                )
                for question_id in exam_questions_map.get(exam_id, []):
                    task_id = async_task(
                        evaluate_question_task,
                        eval_stub.id,
                        question_id,
                        user_prompt,
                        group=f"eval:{eval_stub.id}",
                        timeout=EVALUATION_TASK_TIMEOUT,
                    )
                    task_ids.append(task_id)

    total_tasks = len(task_ids)

    return JsonResponse(
        {
            "status": "queued",
            "task_ids": task_ids,
            "evaluation_ids": evaluation_ids,
            "evaluations": evaluations_meta,
            "total_tasks": total_tasks,
            "message": f"Batch evaluation queued: {total_tasks} question task(s)",
        }
    )


@login_required
def batch_evaluations_view(request):
    user = request.user
    exams = Exam.objects.filter(user=user)
    exams = exams.annotate(
        eval_count=Count("evaluation", filter=Q(evaluation__exam__user=user))
    )
    courses = Course.objects.filter(user=user)

    local_models, external_models = get_models_for_user(user)

    local_models = local_models.annotate(
        eval_count=Count("evaluation", filter=Q(evaluation__exam__user=user))
    )
    external_models = external_models.annotate(
        eval_count=Count("evaluation", filter=Q(evaluation__exam__user=user))
    )

    courses_with_exams = {}
    for course in courses:
        exams_for_course = exams.filter(course=course)
        if exams_for_course.exists():
            courses_with_exams[course] = exams_for_course

    if request.method == "POST":
        models = list(local_models) + list(external_models)
        return handle_batch_evaluations_post(request, user, exams, models)

    return render(
        request,
        "batch_evaluations.html",
        {
            "local_models": local_models,
            "external_models": external_models,
            "subjects_with_exams": courses_with_exams,
        },
    )

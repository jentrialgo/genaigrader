import json

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from genaigrader.models import Evaluation, QuestionEvaluation
from genaigrader.services.llm_service import generate_prompt

# Maximum number of IDs accepted by the batch endpoint. The previous GET
# implementation was constrained by the URL line-length limit (~8 KB); using a
# POST body removes that limit but we still cap the input to bound the work.
MAX_BATCH_IDS = 1000


@login_required
def evaluation_status(request, eval_id):
    """
    Return the current status of an Evaluation.

    Counts actual QuestionEvaluation rows rather than django-q2 task
    records so the progress bar accurately reflects completed questions.
    """
    evaluation = get_object_or_404(
        Evaluation.objects.select_related("exam", "model", "exam__course"),
        id=eval_id,
        exam__course__user=request.user,
    )

    completed = QuestionEvaluation.objects.filter(evaluation=evaluation).count()

    return JsonResponse(
        {
            "evaluation_id": evaluation.id,
            "exam_id": evaluation.exam_id,
            "model_id": evaluation.model_id,
            "status": evaluation.status,
            "completed_tasks": completed,
            "total_tasks": evaluation.total_questions,
            "grade": evaluation.grade if evaluation.status == "completed" else None,
            "time": evaluation.time if evaluation.status == "completed" else None,
            "failed_question_id": evaluation.failed_question_id,
            "failed_reason": evaluation.failed_reason,
        }
    )


@login_required
def batch_evaluation_status(request):
    """
    Return the current status for a batch of Evaluation IDs.

    Accepts either:

    * ``GET /batch-evaluation-status/?ids=1,2,3`` (kept for backwards
      compatibility; subject to the URL line-length limit).
    * ``POST /batch-evaluation-status/`` with a JSON body
      ``{"ids": [1, 2, 3]}`` (or ``{"ids": "1,2,3"}``). Recommended for large
      batches as it is not constrained by URL length.

    Both forms return ``{"status": "ok", "results": [...]}`` where the results
    are ordered to match the input order. Unknown, non-numeric, or non-owned
    IDs are reported as ``status: "not_found"``.
    """
    ids_param = None

    if request.method == "POST":
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, TypeError):
            return JsonResponse(
                {"status": "error", "message": "Invalid JSON body"},
                status=400,
            )
        ids_param = payload.get("ids")
    else:
        ids_param = request.GET.get("ids")

    if ids_param is None or ids_param == "":
        return JsonResponse(
            {
                "status": "error",
                "message": "Missing 'ids' parameter",
            },
            status=400,
        )

    # Normalise to a list of raw string IDs preserving input order.
    if isinstance(ids_param, (list, tuple)):
        raw_ids = [str(i).strip() for i in ids_param if str(i).strip()]
    else:
        raw_ids = [e.strip() for e in str(ids_param).split(",") if e.strip()]

    if len(raw_ids) > MAX_BATCH_IDS:
        return JsonResponse(
            {
                "status": "error",
                "message": "Too many ids (max %d)" % MAX_BATCH_IDS,
            },
            status=400,
        )

    # Parse to integers. Non-numeric IDs become "not_found" entries (we keep
    # the original string representation for the response to avoid leaking
    # the parse failure differently than the previous implementation).
    typed_ids = []  # list of (int, original_string)
    for raw in raw_ids:
        try:
            typed_ids.append((int(raw), raw))
        except (ValueError, TypeError):
            typed_ids.append((None, raw))

    int_ids = [tid for tid, _ in typed_ids if tid is not None]

    results_by_id = {}
    if int_ids:
        evaluations = (
            Evaluation.objects.filter(id__in=int_ids, exam__course__user=request.user)
            .select_related("exam", "model", "exam__course")
            .in_bulk()
        )
        # Single grouped query for per-evaluation completed counts, replacing
        # the previous "one COUNT() per evaluation" N+1 pattern.
        counts = (
            QuestionEvaluation.objects.filter(evaluation_id__in=int_ids)
            .values("evaluation_id")
            .annotate(completed=Count("id"))
        )
        counts_by_id = {c["evaluation_id"]: c["completed"] for c in counts}

        for eval_id_int, evaluation in evaluations.items():
            results_by_id[eval_id_int] = {
                "evaluation_id": evaluation.id,
                "exam_id": evaluation.exam_id,
                "model_id": evaluation.model_id,
                "model_name": evaluation.model.description,
                "exam_name": evaluation.exam.description,
                "course_name": evaluation.exam.course.name,
                "status": evaluation.status,
                "completed_tasks": counts_by_id.get(evaluation.id, 0),
                "total_tasks": evaluation.total_questions,
                "grade": (
                    evaluation.grade if evaluation.status == "completed" else None
                ),
                "time": (evaluation.time if evaluation.status == "completed" else None),
                "failed_question_id": evaluation.failed_question_id,
                "failed_reason": evaluation.failed_reason,
            }

    # Build result list preserving the original input order; missing IDs
    # (unknown, non-numeric, or not owned by the user) become "not_found".
    results = []
    for tid, raw in typed_ids:
        if tid is not None and tid in results_by_id:
            results.append(results_by_id[tid])
        else:
            results.append(
                {
                    "evaluation_id": tid if tid is not None else raw,
                    "status": "not_found",
                }
            )

    return JsonResponse(
        {
            "status": "ok",
            "results": results,
        }
    )


@login_required
def evaluation_questions(request, eval_id):
    """
    Return per-question details for an Evaluation.

    Returns a list of question evaluations with prompt, response,
    correct option, correctness flag, and timing.
    """
    evaluation = get_object_or_404(
        Evaluation.objects.select_related("exam", "model", "exam__course"),
        id=eval_id,
        exam__course__user=request.user,
    )

    # Stable ordering: enumerate ALL exam questions so question_number never
    # shifts as tasks finish out of order.
    all_questions = list(
        evaluation.exam.question_set.all()
        .select_related("correct_option")
        .prefetch_related("questionoption_set")
        .order_by("id")
    )
    qe_qs = QuestionEvaluation.objects.filter(evaluation=evaluation).select_related(
        "question"
    )
    qe_map = {qe.question_id: qe for qe in qe_qs}

    questions = []
    for idx, question in enumerate(all_questions, start=1):
        qe = qe_map.get(question.id)
        if not qe:
            continue
        correct_option = question.correct_option
        response_text = qe.response_text.strip().lower()
        questions.append(
            {
                "question_number": idx,
                "question_id": question.id,
                "question_prompt": generate_prompt(question, "")["question_prompt"],
                "response": response_text[0] if response_text else "",
                "correct_option": correct_option.content if correct_option else "",
                "is_correct": qe.is_correct,
                "question_time": qe.question_time,
            }
        )

    return JsonResponse(
        {
            "evaluation_id": evaluation.id,
            "status": evaluation.status,
            "model_name": evaluation.model.description,
            "exam_name": evaluation.exam.description,
            "course_name": evaluation.exam.course.name,
            "total_questions": evaluation.total_questions,
            "questions": questions,
        }
    )

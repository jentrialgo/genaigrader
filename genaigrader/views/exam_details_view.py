from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from genaigrader.models import Evaluation, Exam, Question
from genaigrader.services.graphics_service import (
    compute_model_statistics,
    process_evaluations_for_graphics,
)
from genaigrader.services.model_service import DEFAULT_MODEL_COLOR
from genaigrader.services.question_analytics_service import calculate_question_analytics


@login_required
def exam_detail(request, exam_id):
    exam = get_object_or_404(
        Exam.objects.select_related("course", "user").prefetch_related(
            "question_set__questionoption_set",
            "question_set__correct_option",
            "evaluation_set__model",
        ),
        id=exam_id,
        course__user=request.user,
    )

    evaluations = exam.evaluation_set.all()
    model_values = process_evaluations_for_graphics(evaluations)
    model_averages, time_averages = compute_model_statistics(model_values)

    return render(
        request,
        "exam_detail.html",
        {
            "exam": exam,
            "course": exam.course,
            "questions": exam.question_set.all(),
            "evaluations": evaluations,
            "model_averages": model_averages,
            "time_averages": time_averages,
            "default_model_color": DEFAULT_MODEL_COLOR,
        },
    )


@login_required
@require_http_methods(["DELETE"])
def delete_evaluation(request, eval_id):
    evaluation = (
        Evaluation.objects.select_related("exam__course")
        .filter(id=eval_id, exam__course__user=request.user)
        .first()
    )
    if evaluation is None:
        return JsonResponse(
            {"status": "error", "message": "Evaluation not found"}, status=404
        )
    evaluation.delete()
    return JsonResponse({"status": "success"})


@login_required
@require_http_methods(["GET"])
def question_analytics(request, question_id):
    try:
        question = (
            Question.objects.select_related("exam__course")
            .filter(id=question_id, exam__course__user=request.user)
            .first()
        )
        if question is None:
            return JsonResponse(
                {"success": False, "error": "Question not found"}, status=404
            )
        stats = calculate_question_analytics(question)
        return JsonResponse({"success": True, "data": stats})
    except (ValueError, TypeError, ValidationError) as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

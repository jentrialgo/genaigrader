from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from genaigrader.models import Course, Evaluation
from genaigrader.services.graphics_service import (
    compute_model_statistics,
    process_evaluations_for_graphics,
)


@login_required
def analysis_view(request):
    # Get courses and related exams
    user_courses = Course.objects.filter(user=request.user).prefetch_related("exam_set")

    course_data = []

    # Process each course
    for course in user_courses:
        evaluations = Evaluation.objects.filter(exam__in=course.exam_set.all())

        if evaluations.exists():
            model_values = process_evaluations_for_graphics(evaluations)
            model_averages, time_averages = compute_model_statistics(model_values)
        else:
            model_averages, time_averages = [], []

        course_data.append(
            {
                "course": {"id": course.id, "name": course.name},
                "model_averages": model_averages,
                "time_averages": time_averages,
            }
        )

    # Process global statistics
    all_evals = Evaluation.objects.filter(exam__course__user=request.user)

    if all_evals.exists():
        global_values = process_evaluations_for_graphics(all_evals)
        overall_model_averages, overall_time_averages = compute_model_statistics(
            global_values
        )
    else:
        overall_model_averages, overall_time_averages = [], []

    return render(
        request,
        "analysis.html",
        {
            "course_data": course_data,
            "overall_model_averages": overall_model_averages,
            "overall_time_averages": overall_time_averages,
        },
    )
